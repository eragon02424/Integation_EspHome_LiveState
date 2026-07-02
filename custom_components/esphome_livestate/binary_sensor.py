"""Binary sensor platform for ESPHome LiveState.

Each device sub-entry owns exactly one binary_sensor entity.
The entity is attached to the existing ESPHome HA device via MAC address.
"""
from __future__ import annotations
import logging
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    coordinator: ESPHomeLiveStateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_name = entry.data["device_name"]

    mac = ""
    for d in coordinator.data or []:
        if d.get("name") == device_name:
            mac = d.get("mac_address") or ""
            break

    if not mac:
        _LOGGER.warning("No MAC found for %s, skipping entity creation", device_name)
        return

    async_add_entities([ESPHomeLiveStateSensor(coordinator, device_name, mac, entry.entry_id)])


class ESPHomeLiveStateSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Verbindungs Status"

    def __init__(
        self,
        coordinator: ESPHomeLiveStateCoordinator,
        device_name: str,
        mac: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_name = device_name
        self._mac = mac
        self._attr_unique_id = f"esphome_livestate_{device_name}_verbindungsstatus"

    async def async_added_to_hass(self) -> None:
        """Force an immediate state write on startup."""
        await super().async_added_to_hass()
        self.async_write_ha_state()

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
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self._current_device
        if not device:
            return {}
        return {
            "last_seen": device.get("last_seen"),
            "address": device.get("address"),
        }
