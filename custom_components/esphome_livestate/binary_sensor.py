"""Binary sensor platform for ESPHome LiveState.

Only creates entities for devices that already exist in the HA device registry
(matched via MAC address). Devices without a known MAC or without an existing
HA device are silently skipped — they will be picked up on a future poll once
their MAC becomes available and they have been registered in HA via ESPHome.
"""
from __future__ import annotations
import logging
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DOMAIN
from .coordinator import ESPHomeLiveStateCoordinator

_LOGGER = logging.getLogger(__name__)


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
            # Skip devices without a MAC — we cannot attach them to an existing HA device
            if not mac:
                _LOGGER.debug("Skipping %s: no MAC address known yet", name)
                continue
            # Skip devices that do not yet exist in the HA device registry
            existing = dev_reg.async_get_device(
                connections={(CONNECTION_NETWORK_MAC, mac)}
            )
            if not existing:
                _LOGGER.debug("Skipping %s: MAC %s not in HA device registry", name, mac)
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
        # MAC is guaranteed to be set here (checked in async_setup_entry)
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
