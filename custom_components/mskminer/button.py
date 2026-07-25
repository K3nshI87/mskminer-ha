"""Button entities for MSKMiner — restart, reboot, blink."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Coroutine, Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MSKMinerAPI
from .const import DOMAIN
from .coordinator import MinerCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class MinerButtonDescription(ButtonEntityDescription):
    action: Callable[[MSKMinerAPI], Coroutine[Any, Any, None]]


BUTTON_TYPES: tuple[MinerButtonDescription, ...] = (
    MinerButtonDescription(
        key="restart_miner",
        name="Restart Miner",
        icon="mdi:restart",
        action=lambda api: api.restart_miner(),
    ),
    MinerButtonDescription(
        key="reboot_device",
        name="Reboot Device",
        icon="mdi:power-cycle",
        action=lambda api: api.reboot_device(),
    ),
    MinerButtonDescription(
        key="blink",
        name="Blink LED",
        icon="mdi:led-on",
        action=lambda api: api.blink_start(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, MinerCoordinator] = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerButton] = []
    for ip, coordinator in coordinators.items():
        for desc in BUTTON_TYPES:
            entities.append(MinerButton(coordinator.api, desc, ip))

    async_add_entities(entities)


class MinerButton(ButtonEntity):
    entity_description: MinerButtonDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        api: MSKMinerAPI,
        description: MinerButtonDescription,
        ip: str,
    ) -> None:
        self.entity_description = description
        self._api = api
        self._attr_unique_id = f"mskminer_{ip.replace('.', '_')}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ip)},
        )

    async def async_press(self) -> None:
        try:
            await self.entity_description.action(self._api)
        except Exception as err:
            _LOGGER.error("Button %s failed for %s: %s", self.entity_description.key, self._api.host, err)
