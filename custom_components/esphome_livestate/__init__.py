"""ESPHome LiveState - creates Online/Offline binary_sensor entities for ESPHome devices."""
from __future__ import annotations
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from .coordinator import ESPHomeLiveStateCoordinator

_LOGGER = logging.getLogger(__name__)
DOMAIN = "esphome_livestate"
PLATFORMS = ["binary_sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ESPHomeLiveStateCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to MCP ESPHome addon: {err}") from err
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
