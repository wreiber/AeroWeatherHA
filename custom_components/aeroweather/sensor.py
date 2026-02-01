from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AeroWeatherCoordinator


@dataclass(frozen=True)
class AeroWeatherSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any], str], str | None]
    attrs_fn: Callable[[dict[str, Any], str], dict[str, Any]]


DESCRIPTIONS = [
    AeroWeatherSensorDescription(
        key="metar",
        name="METAR",
        icon="mdi:weather-windy",
        value_fn=lambda d, i: (d.get("metar", {}).get(i) or {}).get("rawOb"),
        attrs_fn=lambda d, i: d.get("metar", {}).get(i, {}),
    ),
    AeroWeatherSensorDescription(
        key="taf",
        name="TAF",
        icon="mdi:weather-cloudy-clock",
        value_fn=lambda d, i: (d.get("taf", {}).get(i) or {}).get("rawTAF"),
        attrs_fn=lambda d, i: d.get("taf", {}).get(i, {}),
    ),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: AeroWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        AeroWeatherSensor(coordinator, icao, desc)
        for icao in coordinator.icaos
        for desc in DESCRIPTIONS
    ]
    async_add_entities(entities)


class AeroWeatherSensor(CoordinatorEntity[AeroWeatherCoordinator], SensorEntity):
    def __init__(self, coordinator, icao, description):
        super().__init__(coordinator)
        self._icao = icao
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{icao}_{description.key}"
        self._attr_name = f"{icao} {description.name}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(
            self.coordinator.data or {}, self._icao
        )

    @property
    def extra_state_attributes(self):
        return self.entity_description.attrs_fn(
            self.coordinator.data or {}, self._icao
        )
