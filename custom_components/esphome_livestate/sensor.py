"""DEPRECATED — no longer used.

The "Zuletzt Online" / "Zuletzt Offline" duration sensors previously
defined here were removed in v0.5.0: redundant with the
"Verbindungs Status" binary_sensor, whose state and history already
carry everything needed (current status, last change, duration since
last change) via the standard entity history.

Platform.SENSOR was removed from PLATFORMS in __init__.py, so this file
is never imported. Kept only as a stub; not wired into the integration.
"""
