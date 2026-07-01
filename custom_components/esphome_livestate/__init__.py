"""ESPHome LiveState integration.

Architecture:
- One 'hub' config entry created by the user via the UI (contains addon URL + token)
- One 'device' config entry per discovered ESP device, created automatically
  when the hub coordinator first sees a device with a known MAC in the HA ESPHome
  device registry. These entries appear as the integration source in the device page.

The hub entry owns the coordinator that polls /devices every 15s.
Each device entry owns exactly one binary_sensor entity.
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
PLATFORMS = [Platform.BINARY_SENSOR]

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

    # Store hub data BEFORE _sync_device_entries so device sub-entries can find it
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Sync on every coordinator update (new devices appear, stale ones removed)
    async def _on_update():
        await _sync_device_entries(hass, entry, coordinator)

    entry.async_on_unload(
        coordinator.async_add_listener(lambda: hass.async_create_task(_on_update()))
    )

    # Initial sync now that hass.data is populated
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
    """Create sub-entries for new devices, remove sub-entries for gone devices."""
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

    dev_reg = dr.async_get(hass)
    devices = coordinator.data or []

    # Devices with a MAC that are registered under the ESPHome integration in HA
    valid_device_names: set[str] = set()
    for device in devices:
        name = device.get("name", "")
        mac = device.get("mac_address") or ""
        if not name or not mac:
            continue
        for ha_device in dev_reg.devices.values():
            if (CONNECTION_NETWORK_MAC, mac) not in ha_device.connections:
                continue
            for cfg_id in ha_device.config_entries:
                cfg = hass.config_entries.async_get_entry(cfg_id)
                if cfg and cfg.domain == "esphome":
                    valid_device_names.add(name)
                    break

    # Existing device sub-entries for this hub
    existing: dict[str, ConfigEntry] = {
        e.data["device_name"]: e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get("entry_type") == ENTRY_TYPE_DEVICE
        and e.data.get("hub_entry_id") == hub_entry.entry_id
    }

    # Create missing sub-entries
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

    # Remove sub-entries for devices no longer valid
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

    # Hub: remove all device sub-entries and their entities first
    ent_reg = er.async_get(hass)
    for e in list(hass.config_entries.async_entries(DOMAIN)):
        if (
            e.data.get("entry_type") == ENTRY_TYPE_DEVICE
            and e.data.get("hub_entry_id") == entry.entry_id
        ):
            # Remove all entities belonging to this device entry from the registry
            for entity in er.async_entries_for_config_entry(ent_reg, e.entry_id):
                ent_reg.async_remove(entity.entity_id)
            await hass.config_entries.async_remove(e.entry_id)

    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
