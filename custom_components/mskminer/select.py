"""Select entity for MSKMiner cooling mode."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)

COOL_MODE_OPTIONS = ["fan", "water", "liquid"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, MinerCoordinator] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CoolingModeSelect(coordinator, ip)
        for ip, coordinator in coordinators.items()
    )


class CoolingModeSelect(CoordinatorEntity[MinerCoordinator], SelectEntity):
    """Select entity to switch cooling mode (fan / water / liquid)."""

    _attr_has_entity_name = True
    _attr_name = "Cooling Mode"
    _attr_icon = "mdi:fan"
    _attr_options = COOL_MODE_OPTIONS

    def __init__(self, coordinator: MinerCoordinator, ip: str) -> None:
        super().__init__(coordinator)
        self._ip = ip
        self._attr_unique_id = f"mskminer_{ip.replace('.', '_')}_cool_mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, ip)})

    @property
    def current_option(self) -> str | None:
        if not self.coordinator.data:
            return None
        mode = self.coordinator.data.get("cooling_mode")
        return mode if mode in COOL_MODE_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.api.set_cool_mode(option)
        await self.coordinator.async_refresh()
