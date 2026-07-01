"""Config flow for ESPHome LiveState."""
from __future__ import annotations
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from . import DOMAIN


async def _fetch_devices(url: str, token: str) -> tuple[str | None, list[dict]]:
    """Fetch devices from addon. Returns (error_code, devices).
    
    error_code is one of: None (success), "cannot_connect", "invalid_auth"
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url.rstrip('/')}/devices",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    return "invalid_auth", []
                if resp.status != 200:
                    return "cannot_connect", []
                return None, await resp.json()
    except Exception:
        return "cannot_connect", []


class ESPHomeLiveStateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            url = user_input["addon_url"].rstrip("/")
            token = user_input.get("bearer_token", "")

            error_code, devices = await _fetch_devices(url, token)

            if error_code:
                errors["base"] = error_code
            elif not any(d.get("mac_address") for d in devices):
                errors["base"] = "no_mac_found"
            else:
                return self.async_create_entry(
                    title="ESPHome LiveState",
                    data={"addon_url": url, "bearer_token": token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("addon_url", default="http://localhost:8090"): str,
                vol.Required("bearer_token", default=""): str,
            }),
            errors=errors,
        )
