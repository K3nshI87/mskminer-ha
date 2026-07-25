"""Switch entity for pausing / resuming mining."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, MinerCoordinator] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MiningSwitchEntity(coordinator, ip)
        for ip, coordinator in coordinators.items()
    )


class MiningSwitchEntity(CoordinatorEntity[MinerCoordinator], SwitchEntity):
    """Switch that pauses/resumes mining. State mirrors miner_stopped field."""

    _attr_has_entity_name = True
    _attr_name = "Mining"
    _attr_icon = "mdi:pickaxe"

    def __init__(self, coordinator: MinerCoordinator, ip: str) -> None:
        super().__init__(coordinator)
        self._ip = ip
        self._attr_unique_id = f"mskminer_{ip.replace('.', '_')}_mining"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, ip)})

    @property
    def is_on(self) -> bool:
        """True when mining is running (miner_stopped == 'started')."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("miner_stopped") != "stopped"

    async def async_turn_on(self, **kwargs) -> None:
        """Resume mining."""
        await self.coordinator.api.resume_mining()
        await self.coordinator.async_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Pause mining."""
        await self.coordinator.api.pause_mining()
        await self.coordinator.async_refresh()
