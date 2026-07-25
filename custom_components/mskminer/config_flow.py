"""Config flow: network scan → add all found miners."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import InvalidAuth, discover_miners
from .const import (
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    DOMAIN,
    CONNECT_TIMEOUT,
    SCAN_CONCURRENCY,
)

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required("ip_range", default="192.168.1.0/24"): str,
        vol.Required("username", default=DEFAULT_USERNAME): str,
        vol.Required("password", default=DEFAULT_PASSWORD): str,
    }
)


class MSKMinerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup: scan network and save found miners."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_range = user_input["ip_range"].strip()
            username = user_input["username"]
            password = user_input["password"]

            try:
                miners = await discover_miners(
                    ip_range,
                    username,
                    password,
                    connect_timeout=CONNECT_TIMEOUT,
                    concurrency=SCAN_CONCURRENCY,
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during network scan")
                errors["base"] = "cannot_connect"
            else:
                if not miners:
                    errors["base"] = "no_miners_found"
                else:
                    _LOGGER.info(
                        "MSKMiner discovery found %d device(s): %s",
                        len(miners),
                        miners,
                    )
                    return self.async_create_entry(
                        title=f"MSKMiner ({ip_range})",
                        data={
                            "ip_range": ip_range,
                            "username": username,
                            "password": password,
                            "miners": miners,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
            description_placeholders={
                "example": "192.168.1.0/24 or 192.168.1.1-254"
            },
        )
