"""MSKMiner integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import MSKMinerAPI
from .const import DOMAIN
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    miners: list[str] = entry.data["miners"]
    username: str = entry.data["username"]
    password: str = entry.data["password"]

    coordinators: dict[str, MinerCoordinator] = {}
    for ip in miners:
        api = MSKMinerAPI(ip, username, password)
        coordinator = MinerCoordinator(hass, api)
        # Don't raise on first refresh — a temporarily offline miner
        # will show unavailable entities and retry on next interval.
        await coordinator.async_refresh()
        coordinators[ip] = coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinators: dict[str, MinerCoordinator] = hass.data[DOMAIN].pop(
            entry.entry_id, {}
        )
        for coordinator in coordinators.values():
            await coordinator.api.close()
    return unloaded
