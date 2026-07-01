"""Config flow for ESPHome LiveState."""
from __future__ import annotations
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from . import DOMAIN


async def _fetch_devices(url: str, token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{url.rstrip('/')}/devices",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                raise ConnectionError(f"HTTP {resp.status}")
            return await resp.json()


class ESPHomeLiveStateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            url = user_input["addon_url"].rstrip("/")
            token = user_input.get("bearer_token", "")

            try:
                devices = await _fetch_devices(url, token)
            except Exception:
                # Addon not reachable at all
                errors["base"] = "cannot_connect"
                devices = []

            if not errors:
                # Check that at least one device has a MAC address.
                # If no MACs are present the addon has not yet connected to any
                # ESP device and attaching entities to the right HA device would
                # be impossible.
                devices_with_mac = [d for d in devices if d.get("mac_address")]
                if not devices_with_mac:
                    errors["base"] = "no_mac_found"

            if not errors:
                return self.async_create_entry(
                    title="ESPHome LiveState",
                    data={"addon_url": url, "bearer_token": token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("addon_url", default="http://localhost:8090"): str,
                vol.Optional("bearer_token", default=""): str,
            }),
            errors=errors,
        )
