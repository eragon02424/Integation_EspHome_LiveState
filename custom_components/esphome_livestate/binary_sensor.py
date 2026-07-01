"""Binary sensor platform for ESPHome LiveState.

Only creates entities for devices that:
1. Have a known MAC address
2. Already exist in the HA device registry
3. Are registered under the 'esphome' integration domain

This prevents accidentally attaching to non-ESPHome devices (e.g. FritzBox
tracked devices) that happen to share the same MAC address.
"""
from __future__ import annotations
import logging
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN
from .coordinator import ESPHomeLiveStateCoordinator

_LOGGER = logging.getLogger(__name__)

ESPHOME_DOMAIN = "esphome"


def _is_esphome_device(dev_reg: dr.DeviceRegistry, mac: str) -> dr.DeviceEntry | None:
    """Return the device entry if a device with this MAC exists AND belongs to ESPHome.

    HA can have multiple device entries sharing the same MAC (e.g. the actual
    ESPHome device and a FritzBox tracked device). We only want the one that
    was registered by the ESPHome integration, identified by having at least
    one config entry whose domain is 'esphome'.
    """
    # async_get_device returns only one entry even if multiple share the MAC.
    # We iterate all devices to find one that both matches the MAC and has
    # an ESPHome config entry.
    for device in dev_reg.devices.values():
        if (CONNECTION_NETWORK_MAC, mac) not in device.connections:
            continue
        # Check if any config entry for this device belongs to ESPHome
        for entry_id in device.config_entries:
            entry = dev_reg.hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == ESPHOME_DOMAIN:
                return device
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ESPHomeLiveStateCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    def _add_new_entities():
        dev_reg = dr.async_get(hass)
        new_entities = []
        for device in coordinator.data or []:
            name = device.get("name", "")
            mac = device.get("mac_address") or ""
            if not name or name in known:
                continue
            if not mac:
                _LOGGER.debug("Skipping %s: no MAC address known yet", name)
                continue
            existing = _is_esphome_device(dev_reg, mac)
            if not existing:
                _LOGGER.debug(
                    "Skipping %s: MAC %s not found in HA device registry under ESPHome integration",
                    name, mac,
                )
                continue
            known.add(name)
            new_entities.append(ESPHomeLiveStateSensor(coordinator, device))
        if new_entities:
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


class ESPHomeLiveStateSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Online"

    def __init__(self, coordinator: ESPHomeLiveStateCoordinator, device_data: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._device_name = device_data["name"]
        self._mac = device_data.get("mac_address") or ""
        self._attr_unique_id = f"esphome_livestate_{self._device_name}_online"

    @property
    def _current_device(self) -> dict | None:
        for d in self.coordinator.data or []:
            if d.get("name") == self._device_name:
                return d
        return None

    @property
    def is_on(self) -> bool | None:
        device = self._current_device
        if device is None:
            return None
        return device.get("online", False)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            name=self._device_name,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self._current_device
        if not device:
            return {}
        return {"last_seen": device.get("last_seen"), "address": device.get("address")}
