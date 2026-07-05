"""ESPHome LiveState integration.

Architecture:
- One 'hub' config entry created by the user via the UI (contains addon URL + token)
- One 'device' config entry per discovered ESP device, created automatically
  when the hub coordinator first sees a device with a known MAC in the HA device
  registry. These entries appear as the integration source in the device page.

The hub entry owns the coordinator that polls /devices every 15s.
Each device entry owns one binary_sensor entity (Verbindungs Status) and two
sensor entities (Zuletzt Online / Zuletzt Offline).

NOTE: We do NOT filter by cfg.domain == "esphome" because in this setup the ESP
devices are registered via MQTT, not via the native ESPHome integration. We only
require that a device with the matching MAC exists somewhere in the HA device
registry.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .coordinator import ESPHomeLiveStateCoordinator

_LOGGER = logging.getLogger(__name__)

DOMAIN = "esphome_livestate"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

ENTRY_TYPE_HUB = "hub"
ENTRY_TYPE_DEVICE = "device"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_type = entry.data.get("entry_type", ENTRY_TYPE_HUB)
    if entry_type == ENTRY_TYPE_HUB:
        return await _async_setup_hub(hass, entry)
    if entry_type == ENTRY_TYPE_DEVICE:
        return await _async_setup_device(hass, entry)
    return False


async def _async_setup_hub(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ESPHomeLiveStateCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to MCP ESPHome addon: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    async def _on_update():
        await _sync_device_entries(hass, entry, coordinator)

    entry.async_on_unload(
        coordinator.async_add_listener(lambda: hass.async_create_task(_on_update()))
    )

    await _sync_device_entries(hass, entry, coordinator)
    return True


async def _async_setup_device(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub_entry_id = entry.data.get("hub_entry_id")
    hub_data = hass.data.get(DOMAIN, {}).get(hub_entry_id)
    if not hub_data:
        raise ConfigEntryNotReady("Hub entry not yet loaded")

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": hub_data["coordinator"]}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _sync_device_entries(
    hass: HomeAssistant,
    hub_entry: ConfigEntry,
    coordinator: ESPHomeLiveStateCoordinator,
) -> None:
    """Create sub-entries for new devices, remove sub-entries for gone devices.

    A device qualifies if:
    1. The addon reports a mac_address for it
    2. A device with that MAC exists in the HA device registry (any integration)
    """
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

    dev_reg = dr.async_get(hass)
    devices = coordinator.data or []

    # Build lookup: mac -> ha_device for fast matching
    mac_to_ha_device: dict[str, object] = {}
    for ha_device in dev_reg.devices.values():
        for conn_type, conn_val in ha_device.connections:
            if conn_type == CONNECTION_NETWORK_MAC:
                mac_to_ha_device[conn_val.upper()] = ha_device

    valid_device_names: set[str] = set()
    for device in devices:
        name = device.get("name", "")
        mac = (device.get("mac_address") or "").upper()
        if not name or not mac:
            continue
        if mac in mac_to_ha_device:
            valid_device_names.add(name)
        else:
            _LOGGER.debug("Skipping %s: MAC %s not in HA device registry", name, mac)

    _LOGGER.info("ESPHome LiveState: %d valid devices found", len(valid_device_names))

    existing: dict[str, ConfigEntry] = {
        e.data["device_name"]: e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get("entry_type") == ENTRY_TYPE_DEVICE
        and e.data.get("hub_entry_id") == hub_entry.entry_id
    }

    for name in valid_device_names:
        if name not in existing:
            _LOGGER.info("Creating device entry for %s", name)
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "device_auto"},
                    data={
                        "entry_type": ENTRY_TYPE_DEVICE,
                        "hub_entry_id": hub_entry.entry_id,
                        "device_name": name,
                        "addon_url": hub_entry.data["addon_url"],
                        "bearer_token": hub_entry.data.get("bearer_token", ""),
                    },
                )
            )

    for name, sub_entry in existing.items():
        if name not in valid_device_names:
            _LOGGER.info("Removing device entry for %s", name)
            hass.async_create_task(
                hass.config_entries.async_remove(sub_entry.entry_id)
            )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_type = entry.data.get("entry_type", ENTRY_TYPE_HUB)

    if entry_type == ENTRY_TYPE_DEVICE:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok

    ent_reg = er.async_get(hass)
    for e in list(hass.config_entries.async_entries(DOMAIN)):
        if (
            e.data.get("entry_type") == ENTRY_TYPE_DEVICE
            and e.data.get("hub_entry_id") == entry.entry_id
        ):
            for entity in er.async_entries_for_config_entry(ent_reg, e.entry_id):
                ent_reg.async_remove(entity.entity_id)
            await hass.config_entries.async_remove(e.entry_id)

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
