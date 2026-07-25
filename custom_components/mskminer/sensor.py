"""Sensor entities for MSKMiner devices."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _psu(d: dict) -> dict:
    """Shortcut to the nested PSU block."""
    return (
        d.get("get.device.info", {})
        .get("msg", {})
        .get("power", {})
    )


# ---------------------------------------------------------------------------
# Value extractors — exact field names from info_app
# ---------------------------------------------------------------------------

def _hashrate(d: dict) -> float | None:
    return d.get("real_hash_rate")


def _avg_hashrate(d: dict) -> float | None:
    return d.get("avg_hash_rate")


def _temp_outlet(d: dict) -> float | None:
    temp = d.get("temp", {})
    if isinstance(temp, dict):
        return temp.get("outlet")
    return None


def _temp_inlet(d: dict) -> float | None:
    temp = d.get("temp", {})
    if isinstance(temp, dict):
        return temp.get("inlet")
    return None


def _power(d: dict) -> float | None:
    v = d.get("power")
    return float(v) if v is not None else None


def _uptime_hours(d: dict) -> float | None:
    # API returns running_time in seconds
    v = d.get("running_time")
    if v is not None:
        return round(float(v) / 3600, 2)
    return None


def _psu_fan(d: dict) -> float | None:
    # For water-cooled miners the air fans are 0; the PSU fan is in device info
    v = _psu(d).get("fanspeed")
    if v:
        return float(v)
    # Fallback: air fans for non-water-cooled
    fans = d.get("fan_speed", [])
    if isinstance(fans, list):
        active = [f for f in fans if isinstance(f, (int, float)) and f > 0]
        if active:
            return float(round(sum(active) / len(active)))
    return None


def _psu_temp(d: dict) -> float | None:
    v = _psu(d).get("temp0")
    return float(v) if v is not None else None


def _active_pool(d: dict) -> str | None:
    for pool in d.get("pools", []):
        if isinstance(pool, dict) and pool.get("url"):
            return pool["url"]
    return None


def _miner_status(d: dict) -> str | None:
    return d.get("miner_status")


# ---------------------------------------------------------------------------
# Entity descriptions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class MinerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]


SENSOR_TYPES: tuple[MinerSensorDescription, ...] = (
    MinerSensorDescription(
        key="hashrate",
        name="Hashrate",
        icon="mdi:pickaxe",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_hashrate,
    ),
    MinerSensorDescription(
        key="avg_hashrate",
        name="Avg Hashrate",
        icon="mdi:pickaxe",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_avg_hashrate,
    ),
    MinerSensorDescription(
        key="temp_outlet",
        name="Temperature Outlet",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_temp_outlet,
    ),
    MinerSensorDescription(
        key="temp_inlet",
        name="Temperature Inlet",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_temp_inlet,
    ),
    MinerSensorDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=_power,
    ),
    MinerSensorDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-outline",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=_uptime_hours,
    ),
    MinerSensorDescription(
        key="psu_fan",
        name="PSU Fan Speed",
        icon="mdi:fan",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="RPM",
        value_fn=_psu_fan,
    ),
    MinerSensorDescription(
        key="psu_temp",
        name="PSU Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=_psu_temp,
    ),
    MinerSensorDescription(
        key="active_pool",
        name="Active Pool",
        icon="mdi:server-network",
        value_fn=_active_pool,
    ),
    MinerSensorDescription(
        key="miner_status",
        name="Status",
        icon="mdi:information-outline",
        value_fn=_miner_status,
    ),
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, MinerCoordinator] = hass.data[DOMAIN][entry.entry_id]

    entities: list[MinerSensor] = []
    for ip, coordinator in coordinators.items():
        for desc in SENSOR_TYPES:
            entities.append(MinerSensor(coordinator, desc, ip))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

class MinerSensor(CoordinatorEntity[MinerCoordinator], SensorEntity):
    entity_description: MinerSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MinerCoordinator,
        description: MinerSensorDescription,
        ip: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._ip = ip
        self._attr_unique_id = f"mskminer_{ip.replace('.', '_')}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._ip)},
            name=f"MSKMiner {self._ip}",
            model=data.get("miner_type", "MSKMiner"),
            manufacturer=str(data.get("miner_factory", "MSKMiner")).capitalize(),
            sw_version=data.get("version"),
            configuration_url=f"http://{self._ip}",
        )

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        # Hashrate unit comes from API: TH/s, GH/s, etc.
        if self.entity_description.key in ("hashrate", "avg_hashrate"):
            if self.coordinator.data:
                return self.coordinator.data.get("rate_unit", "TH/s")
        return self.entity_description.native_unit_of_measurement
