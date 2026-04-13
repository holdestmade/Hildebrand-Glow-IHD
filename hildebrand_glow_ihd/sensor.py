"""Support for hildebrand glow MQTT sensors."""

from __future__ import annotations
from datetime import datetime, time, timedelta, tzinfo
import json
import logging
import re
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE_ID,
    SIGNAL_STRENGTH_DECIBELS,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_GAS_UNITS,
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DEFAULT_DEVICE_ID,
    DEFAULT_GAS_UNITS,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    MeterInterval,
)

_LOGGER = logging.getLogger(__name__)

# glow/XXXXXXYYYYYY/STATE                   {"software":"v1.8.12","timestamp":"2022-06-11T20:54:53Z","hardware":"GLOW-IHD-01-1v4-SMETS2","ethmac":"1234567890AB","smetsversion":"SMETS2","eui":"12:34:56:78:91:23:45","zigbee":"1.2.5","han":{"rssi":-75,"status":"joined","lqi":100}}
# glow/XXXXXXYYYYYY/SENSOR/electricitymeter {"electricitymeter":{"timestamp":"2022-06-11T20:38:00Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":6613.405,"day":13.252,"week":141.710,"month":293.598,"units":"kWh","mpan":"1234","supplier":"ABC ENERGY","price":{"unitrate":0.04998,"standingcharge":0.24030}}},"power":{"value":0.951,"units":"kW"}}}
# glow/XXXXXXYYYYYY/SENSOR/gasmeter         {"gasmeter":{"timestamp":"2022-06-11T20:53:52Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":17940.852,"day":11.128,"week":104.749,"month":217.122,"units":"kWh","mprn":"1234","supplier":"---","price":{"unitrate":0.07320,"standingcharge":0.17850}}},"power":{"value":0.000,"units":"kW"}}}

STATE_SENSORS = [
    {
        "name": "Smart Meter IHD Software Version",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["software"],
    },
    {
        "name": "Smart Meter IHD Last Seen",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:clock-check-outline",
        "func": lambda js: (
            datetime.fromisoformat(ts) if (ts := js.get("timestamp")) else None
        ),
    },
    {
        "name": "Smart Meter IHD Hardware",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["hardware"],
    },
    {
        "name": "Smart Meter IHD HAN Status",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["han"]["status"],
    },
    {
        "name": "Smart Meter IHD HAN RSSI",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "unit_of_measurement": SIGNAL_STRENGTH_DECIBELS,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["rssi"],
    },
    {
        "name": "Smart Meter IHD HAN LQI",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["lqi"],
    },
]

ELECTRICITY_SENSORS = [
    {
        "name": "Smart Meter Electricity: Export",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["export"]["cumulative"],
    },
    {
        "name": "Smart Meter Electricity: Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["day"],
    },
    {
        "name": "Smart Meter Electricity: Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["week"],
    },
    {
        "name": "Smart Meter Electricity: Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["month"],
    },
    {
        "name": "Smart Meter Electricity: Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "unitrate"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Electricity: Power",
        "device_class": SensorDeviceClass.POWER,
        "unit_of_measurement": UnitOfPower.KILO_WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["power"]["value"],
    },
    {
        "name": "Smart Meter Electricity: Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "meter_interval": MeterInterval.DAY,
        "func": lambda js: round(
            js["electricitymeter"]["energy"]["import"]["price"]["standingcharge"]
            + (
                js["electricitymeter"]["energy"]["import"]["day"]
                * js["electricitymeter"]["energy"]["import"]["price"]["unitrate"]
            ),
            2,
        ),
    },
]

GAS_SENSORS = [
    {
        "name": "Smart Meter Gas: Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulativevol"],
        "ignore_zero_values": True,
        "is_volume_sensor": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol (Today)",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["dayvol"],
        "is_volume_sensor": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol (This week)",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["weekvol"],
        "is_volume_sensor": True,
    },
    {
        "name": "Smart Meter Gas: Import Vol (This month)",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["monthvol"],
        "is_volume_sensor": True,
    },
    {
        "name": "Smart Meter Gas: Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["day"],
    },
    {
        "name": "Smart Meter Gas: Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["week"],
    },
    {
        "name": "Smart Meter Gas: Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["month"],
    },
    {
        "name": "Smart Meter Gas: Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"]["unitrate"],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    {
        "name": "Smart Meter Gas: Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "meter_interval": MeterInterval.DAY,
        "func": lambda js: round(
            (js["gasmeter"]["energy"]["import"]["price"]["standingcharge"] or 0)
            + (
                (js["gasmeter"]["energy"]["import"]["day"] or 0)
                * (js["gasmeter"]["energy"]["import"]["price"]["unitrate"] or 0)
            ),
            2,
        ),
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Meter sensors."""

    device_mac = hass.data[DOMAIN][config_entry.entry_id][CONF_DEVICE_ID]
    topic_prefix = hass.data[DOMAIN][config_entry.entry_id].get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    time_zone_electricity = hass.data[DOMAIN][config_entry.entry_id][CONF_TIME_ZONE_ELECTRICITY]
    time_zone_gas = hass.data[DOMAIN][config_entry.entry_id][CONF_TIME_ZONE_GAS]
    gas_units_config = hass.data[DOMAIN][config_entry.entry_id].get(CONF_GAS_UNITS, DEFAULT_GAS_UNITS)

    device_update_groups = {}

    async def mqtt_message_received(message: ReceiveMessage):
        """Handle received MQTT message."""
        topic = message.topic
        payload = message.payload
        try:
            device_id = topic.split("/")[1]
        except IndexError:
            _LOGGER.debug("Received message on unexpected topic: %s", topic)
            return

        if device_mac == DEFAULT_DEVICE_ID or device_id == device_mac:
            update_groups = await async_get_device_groups(
                device_update_groups,
                async_add_entities,
                device_id,
                time_zone_electricity,
                time_zone_gas,
                topic_prefix,
                gas_units_config,
            )
            _LOGGER.debug("Received message: %s", topic)
            _LOGGER.debug("  Payload: %s", payload)
            for update_group in update_groups:
                update_group.process_update(message)

    data_topic = f"{topic_prefix}/#"

    await mqtt.async_subscribe(hass, data_topic, mqtt_message_received, 1)


async def async_get_device_groups(
    device_update_groups,
    async_add_entities,
    device_id,
    time_zone_electricity,
    time_zone_gas,
    topic_prefix,
    gas_units_config,
):
    # add to update groups if not already there
    if device_id not in device_update_groups:
        _LOGGER.debug("New device found: %s", device_id)

        groups = [
            HildebrandGlowMqttSensorUpdateGroup(
                device_id=device_id,
                topic_regex="STATE",
                meters=STATE_SENSORS,
            ),
            HildebrandGlowMqttSensorUpdateGroup(
                device_id=device_id,
                topic_regex="electricitymeter",
                meters=ELECTRICITY_SENSORS,
                time_zone=time_zone_electricity,
            ),
            HildebrandGlowMqttSensorUpdateGroup(
                device_id=device_id,
                topic_regex="gasmeter",
                meters=GAS_SENSORS,
                time_zone=time_zone_gas,
                gas_units_config=gas_units_config,
            ),
        ]
        async_add_entities(
            [
                sensor_entity
                for update_group in groups
                for sensor_entity in update_group.all_sensors
            ],
        )
        device_update_groups[device_id] = groups

    return device_update_groups[device_id]


class HildebrandGlowMqttSensorUpdateGroup:
    """Representation of Hildebrand Glow MQTT Meter Sensors that all get updated together."""

    def __init__(
        self,
        device_id: str,
        topic_regex: str,
        meters: Iterable,
        time_zone: str | None = None,
        gas_units_config: str | None = None,
    ) -> None:
        """Initialize the sensor collection."""
        self._topic_regex = re.compile(topic_regex)
        self._sensors = [
            HildebrandGlowMqttSensor(
                device_id=device_id,
                time_zone=time_zone,
                gas_units_config=gas_units_config,
                **meter,
            )
            for meter in meters
        ]

    def process_update(self, message: ReceiveMessage) -> None:
        """Process an update from the MQTT broker."""
        topic = message.topic
        payload = message.payload
        if self._topic_regex.search(topic):
            _LOGGER.debug("Matched on %s", self._topic_regex.pattern)
            try:
                parsed_data = json.loads(payload)
                for sensor in self._sensors:
                    try:
                        sensor.process_update(parsed_data)
                    except (KeyError, TypeError, ValueError) as e:
                        _LOGGER.debug(
                            "Could not update sensor %s due to missing or invalid data in payload. Error: %s",
                            sensor.unique_id,
                            e,
                        )
            except json.JSONDecodeError:
                _LOGGER.warning("Could not parse MQTT message as JSON: %s", payload)

    @property
    def all_sensors(self) -> Iterable[HildebrandGlowMqttSensor]:
        """Return all meters."""
        return self._sensors


class HildebrandGlowMqttSensor(SensorEntity):
    """Representation of a room sensor that is updated via MQTT."""

    def __init__(
        self,
        device_id: str,
        time_zone: str | None,
        name: str,
        icon: str,
        device_class: SensorDeviceClass | None,
        unit_of_measurement: str | None,
        state_class: SensorStateClass | None,
        func,
        entity_category: EntityCategory | None = None,
        ignore_zero_values: bool = False,
        meter_interval: MeterInterval | None = None,
        is_volume_sensor: bool = False,
        gas_units_config: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._device_id = device_id
        self._time_zone = time_zone
        self._attr_name = name
        self._attr_icon = icon

        # Handle configurable gas units
        if is_volume_sensor and gas_units_config == "m³":
            self._attr_device_class = SensorDeviceClass.GAS
            self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        else:
            if device_class:
                self._attr_device_class = device_class
            if unit_of_measurement:
                self._attr_native_unit_of_measurement = unit_of_measurement

        if state_class:
            self._attr_state_class = state_class

        self._attr_unique_id = slugify(device_id + "_" + name)
        self._attr_should_poll = False
        self._func = func
        self._attr_entity_category = entity_category
        self._ignore_zero_values = ignore_zero_values
        self._meter_interval = meter_interval

        self._attr_device_info = DeviceInfo(
            connections={("mac", device_id)},
            manufacturer="Hildebrand Technology Limited",
            model="Glow Smart Meter IHD",
            name=f"Glow Smart Meter {device_id}",
        )
        self._attr_native_value = None
        self._last_reset_reported = False
        if state_class == SensorStateClass.TOTAL and meter_interval:
            self._attr_last_reset = None
            self._last_reset_val = None
            self._last_reset_reported = True

    @staticmethod
    def determine_last_reset(
        message_datetime: datetime, meter_timezone: tzinfo, meter_interval: MeterInterval
    ) -> datetime:
        """Return midnight of the meter's reset interval in UTC."""
        meter_datetime = message_datetime.astimezone(meter_timezone)
        meter_midnight = datetime.combine(
            meter_datetime.date(), time.min, meter_datetime.tzinfo
        )
        if meter_interval == MeterInterval.DAY:
            last_reset = meter_midnight
        elif meter_interval == MeterInterval.WEEK:
            last_reset = meter_midnight - timedelta(days=meter_midnight.weekday())
        elif meter_interval == MeterInterval.MONTH:
            last_reset = meter_midnight.replace(day=1)
        elif meter_interval == MeterInterval.YEAR:
            last_reset = meter_midnight.replace(day=1, month=1)
        return last_reset.astimezone(ZoneInfo("UTC"))

    @staticmethod
    def get_message_datetime(mqtt_data) -> datetime:
        """Return the message timestamp as a datetime."""
        timestamp = (
            mqtt_data.get("timestamp")
            or mqtt_data.get("electricitymeter", {}).get("timestamp")
            or mqtt_data.get("gasmeter", {}).get("timestamp")
        )
        try:
            return datetime.fromisoformat(timestamp)
        except (TypeError, ValueError):
            raise ValueError("Valid timestamp not present in MQTT data.")

    def process_update(self, mqtt_data: dict[str, Any]) -> None:
        """Update the state of the sensor."""
        new_value = self._func(mqtt_data)
        if self._ignore_zero_values and new_value == 0:
            _LOGGER.debug(
                "Ignored new value of %s on %s.", new_value, self._attr_unique_id
            )
            return
        self._attr_native_value = new_value

        zone_info = None
        if self._time_zone:
            zone_info = ZoneInfo(self._time_zone)
        elif self.hass is not None and self.hass.config is not None:
            zone_info = ZoneInfo(self.hass.config.time_zone)

        if zone_info and self._last_reset_reported and self._meter_interval:
            try:
                new_last_reset = self.determine_last_reset(
                    self.get_message_datetime(mqtt_data),
                    zone_info,
                    self._meter_interval,
                )
                # Only update if the reset time has changed
                if new_last_reset != self._last_reset_val:
                    self._attr_last_reset = new_last_reset
                    self._last_reset_val = new_last_reset
            except ValueError as e:
                _LOGGER.debug("Could not determine last_reset for %s: %s", self.unique_id, e)

        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {ATTR_DEVICE_ID: self._device_id}
