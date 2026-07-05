"""Sensor platform for ESPHome LiveState.

Two duration sensors per device sub-entry, both derived from the addon's
persisted heartbeat history (survives HA/addon restarts):

- "Zuletzt Online": duration of the last COMPLETED online period. Written
  the moment the device transitions to offline (i.e. it reports how long
  the device was online right before this disconnect).
- "Zuletzt Offline": duration of the last COMPLETED offline period.
  Written the moment the device transitions to online (i.e. it reports
  how long the device was offline right before this reconnect).
"""
from __future__ import annotations
import logging
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
        _LOGGER.warning("No MAC found for %s, skipping duration sensor creation", device_name)
        return

    async_add_entities([
        ESPHomeLiveStateLastOnlineSensor(coordinator, device_name, mac),
        ESPHomeLiveStateLastOfflineSensor(coordinator, device_name, mac),
    ])


class _BaseDurationSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ESPHomeLiveStateCoordinator, device_name: str, mac: str) -> None:
        super().__init__(coordinator)
        self._device_name = device_name
        self._mac = mac

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_write_ha_state()

    @property
    def _current_device(self) -> dict | None:
        for d in self.coordinator.data or []:
            if d.get("name") == self._device_name:
                return d
        return None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(connections={(CONNECTION_NETWORK_MAC, self._mac)})


class ESPHomeLiveStateLastOnlineSensor(_BaseDurationSensor):
    """Duration of the last completed online period (written on disconnect)."""

    _attr_name = "Zuletzt Online"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator, device_name, mac) -> None:
        super().__init__(coordinator, device_name, mac)
        self._attr_unique_id = f"esphome_livestate_{device_name}_zuletzt_online"

    @property
    def native_value(self):
        device = self._current_device
        if not device:
            return None
        val = device.get("last_online_duration_seconds")
        return round(val) if val is not None else None

    @property
    def extra_state_attributes(self):
        device = self._current_device
        if not device:
            return {}
        return {"ended_at": device.get("last_online_ended_at")}


class ESPHomeLiveStateLastOfflineSensor(_BaseDurationSensor):
    """Duration of the last completed offline period (written on reconnect)."""

    _attr_name = "Zuletzt Offline"
    _attr_icon = "mdi:lan-disconnect"

    def __init__(self, coordinator, device_name, mac) -> None:
        super().__init__(coordinator, device_name, mac)
        self._attr_unique_id = f"esphome_livestate_{device_name}_zuletzt_offline"

    @property
    def native_value(self):
        device = self._current_device
        if not device:
            return None
        val = device.get("last_offline_duration_seconds")
        return round(val) if val is not None else None

    @property
    def extra_state_attributes(self):
        device = self._current_device
        if not device:
            return {}
        return {"ended_at": device.get("last_offline_ended_at")}
