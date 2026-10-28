"""Support for hildebrand glow MQTT sensors."""

from __future__ import annotations
from collections.abc import Iterable
from datetime import datetime, time, timedelta, tzinfo
import json
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE_ID,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DOMAIN,
    MeterInterval,
)
from . import GlowConfigEntry

_LOGGER = logging.getLogger(__name__)

MANUFACTURER = "Hildebrand Technology Limited"

# glow/XXXXXXYYYYYY/STATE                   {"software":"v1.8.12","timestamp":"2022-06-11T20:54:53Z","hardware":"GLOW-IHD-01-1v4-SMETS2","ethmac":"1234567890AB","smetsversion":"SMETS2","eui":"12:34:56:78:91:23:45","zigbee":"1.2.5","han":{"rssi":-75,"status":"joined","lqi":100}}
# glow/XXXXXXYYYYYY/SENSOR/electricitymeter {"electricitymeter":{"timestamp":"2022-06-11T20:38:00Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":6613.405,"day":13.252,"week":141.710,"month":293.598,"units":"kWh","mpan":"1234","supplier":"ABC ENERGY","price":{"unitrate":0.04998,"standingcharge":0.24030}}},"power":{"value":0.951,"units":"kW"}}}
# glow/XXXXXXYYYYYY/SENSOR/gasmeter         {"gasmeter":{"timestamp":"2022-06-11T20:53:52Z","energy":{"export":{"cumulative":0.000,"units":"kWh"},"import":{"cumulative":17940.852,"day":11.128,"week":104.749,"month":217.122,"units":"kWh","mprn":"1234","supplier":"---","price":{"unitrate":0.07320,"standingcharge":0.17850}}},"power":{"value":0.000,"units":"kW"}}}

STATE_SENSORS = [
    {
        "key": "Smart Meter IHD Software Version",
        "name": "Software Version",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["software"],
    },
    {
        "key": "Smart Meter IHD Last Seen",
        "name": "Last Seen",
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
        "key": "Smart Meter IHD Hardware",
        "name": "Hardware",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["hardware"],
    },
    {
        "key": "Smart Meter IHD HAN Status",
        "name": "HAN Status",
        "device_class": None,
        "unit_of_measurement": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
        "func": lambda js: js["han"]["status"],
    },
    {
        "key": "Smart Meter IHD HAN RSSI",
        "name": "HAN RSSI",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "unit_of_measurement": SIGNAL_STRENGTH_DECIBELS,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:wifi-strength-outline",
        "func": lambda js: js["han"]["rssi"],
    },
    {
        "key": "Smart Meter IHD HAN LQI",
        "name": "HAN LQI",
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
        "key": "Smart Meter Electricity: Export",
        "name": "Export",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["export"]["cumulative"],
    },
    {
        "key": "Smart Meter Electricity: Import",
        "name": "Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Electricity: Import (Today)",
        "name": "Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["day"],
    },
    {
        "key": "Smart Meter Electricity: Import (This week)",
        "name": "Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["week"],
    },
    {
        "key": "Smart Meter Electricity: Import (This month)",
        "name": "Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["month"],
    },
    {
        "key": "Smart Meter Electricity: Import Unit Rate",
        "name": "Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "unitrate"
        ],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Electricity: Import Standing Charge",
        "name": "Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["electricitymeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Electricity: Power",
        "name": "Power",
        "device_class": SensorDeviceClass.POWER,
        "unit_of_measurement": UnitOfPower.KILO_WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:flash",
        "func": lambda js: js["electricitymeter"]["power"]["value"],
    },
    {
        "key": "Smart Meter Electricity: Cost (Today)",
        "name": "Cost (Today)",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": SensorStateClass.TOTAL,
        "icon": "mdi:cash",
        "meter_interval": MeterInterval.DAY,
        "func": lambda js: round(
            (js["electricitymeter"]["energy"]["import"]["price"]["standingcharge"] or 0)
            + (
                (js["electricitymeter"]["energy"]["import"]["day"] or 0)
                * (js["electricitymeter"]["energy"]["import"]["price"]["unitrate"] or 0)
            ),
            2,
        ),
    },
]

GAS_SENSORS = [
    {
        "key": "Smart Meter Gas: Import",
        "name": "Import",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulative"],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Gas: Import Vol",
        "name": "Import Vol",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["cumulativevol"],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Gas: Import Vol (Today)",
        "name": "Import Vol (Today)",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["dayvol"],
    },
    {
        "key": "Smart Meter Gas: Import Vol (This week)",
        "name": "Import Vol (This week)",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["weekvol"],
    },
    {
        "key": "Smart Meter Gas: Import Vol (This month)",
        "name": "Import Vol (This month)",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["monthvol"],
    },
    {
        "key": "Smart Meter Gas: Import (Today)",
        "name": "Import (Today)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["day"],
    },
    {
        "key": "Smart Meter Gas: Import (This week)",
        "name": "Import (This week)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["week"],
    },
    {
        "key": "Smart Meter Gas: Import (This month)",
        "name": "Import (This month)",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:fire",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["month"],
    },
    {
        "key": "Smart Meter Gas: Import Unit Rate",
        "name": "Import Unit Rate",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP/kWh",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"]["unitrate"],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Gas: Import Standing Charge",
        "name": "Import Standing Charge",
        "device_class": SensorDeviceClass.MONETARY,
        "unit_of_measurement": "GBP",
        "state_class": None,
        "icon": "mdi:cash",
        "func": lambda js: js["gasmeter"]["energy"]["import"]["price"][
            "standingcharge"
        ],
        "ignore_zero_values": True,
    },
    {
        "key": "Smart Meter Gas: Cost (Today)",
        "name": "Cost (Today)",
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
    config_entry: GlowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Smart Meter sensors."""

    entry_data = config_entry.runtime_data
    device_mac = entry_data[CONF_DEVICE_ID]
    topic_prefix = entry_data[CONF_TOPIC_PREFIX]
    time_zone_electricity = entry_data[CONF_TIME_ZONE_ELECTRICITY]
    time_zone_gas = entry_data[CONF_TIME_ZONE_GAS]

    device_update_groups = {}

    async def mqtt_message_received(message: ReceiveMessage):
        """Handle received MQTT message."""
        topic = message.topic
        # Topics look like <prefix>/<device_id>/STATE or <prefix>/<device_id>/SENSOR/...
        topic_parts = topic[len(topic_prefix) + 1 :].split("/")
        if len(topic_parts) < 2 or topic_parts[1] not in ("STATE", "SENSOR"):
            _LOGGER.debug("Received message on unexpected topic: %s", topic)
            return
        device_id = topic_parts[0]

        update_groups = async_get_device_groups(
            hass,
            config_entry,
            device_update_groups,
            async_add_entities,
            device_id,
            time_zone_electricity,
            time_zone_gas,
        )
        _LOGGER.debug("Received message: %s", topic)
        _LOGGER.debug("  Payload: %s", message.payload)
        for update_group in update_groups:
            update_group.process_update(message)

    # Let the broker filter for the configured device ("+" subscribes to all)
    data_topic = f"{topic_prefix}/{device_mac}/#"

    config_entry.async_on_unload(
        await mqtt.async_subscribe(hass, data_topic, mqtt_message_received, 1)
    )


def async_get_device_groups(
    hass: HomeAssistant,
    config_entry: GlowConfigEntry,
    device_update_groups,
    async_add_entities,
    device_id,
    time_zone_electricity,
    time_zone_gas,
):
    # add to update groups if not already there
    if device_id not in device_update_groups:
        _LOGGER.debug("New device found: %s", device_id)

        # The IHD is the hub; the meters are separate devices joined to its HAN.
        # Register it up front so the meters can reference it via via_device_id.
        ihd_device_fields: dict[str, Any] = {
            "identifiers": {(DOMAIN, device_id)},
            "connections": {(CONNECTION_NETWORK_MAC, device_id)},
            "manufacturer": MANUFACTURER,
            "model": "Glow Smart Meter IHD",
            "name": "Smart Meter IHD",
        }
        ihd_device_info = DeviceInfo(**ihd_device_fields)
        ihd_device = dr.async_get(hass).async_get_or_create(
            config_entry_id=config_entry.entry_id, **ihd_device_fields
        )
        electricity_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_id}_electricitymeter")},
            model="Electricity meter",
            name="Smart Meter Electricity",
            via_device_id=ihd_device.id,
        )
        gas_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_id}_gasmeter")},
            model="Gas meter",
            name="Smart Meter Gas",
            via_device_id=ihd_device.id,
        )

        groups = [
            HildebrandGlowMqttSensorUpdateGroup(
                device_id=device_id,
                device_info=ihd_device_info,
                topic_suffix="/STATE",
                meters=STATE_SENSORS,
            ),
            HildebrandGlowMqttSensorUpdateGroup(
                device_id=device_id,
                device_info=electricity_device_info,
                topic_suffix="/SENSOR/electricitymeter",
                meters=ELECTRICITY_SENSORS,
                time_zone=time_zone_electricity,
            ),
            HildebrandGlowMqttSensorUpdateGroup(
                device_id=device_id,
                device_info=gas_device_info,
                topic_suffix="/SENSOR/gasmeter",
                meters=GAS_SENSORS,
                time_zone=time_zone_gas,
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
        device_info: DeviceInfo,
        topic_suffix: str,
        meters: Iterable,
        time_zone: str | None = None,
    ) -> None:
        """Initialize the sensor collection."""
        self._topic_suffix = topic_suffix
        self._sensors = [
            HildebrandGlowMqttSensor(
                device_id=device_id,
                device_info=device_info,
                time_zone=time_zone,
                **meter,
            )
            for meter in meters
        ]

    def process_update(self, message: ReceiveMessage) -> None:
        """Process an update from the MQTT broker."""
        topic = message.topic
        payload = message.payload
        if topic.endswith(self._topic_suffix):
            _LOGGER.debug("Matched on %s", self._topic_suffix)
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

    _attr_has_entity_name = True

    def __init__(
        self,
        device_id: str,
        device_info: DeviceInfo,
        time_zone: str | None,
        key: str,
        name: str,
        icon: str,
        device_class: SensorDeviceClass | None,
        unit_of_measurement: str | None,
        state_class: SensorStateClass | None,
        func,
        entity_category: EntityCategory | None = None,
        ignore_zero_values: bool = False,
        meter_interval: MeterInterval | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._device_id = device_id
        self._zone_info: tzinfo | None = None
        if time_zone:
            try:
                self._zone_info = ZoneInfo(time_zone)
            except (ZoneInfoNotFoundError, ValueError):
                _LOGGER.warning(
                    "Unknown time zone %s, falling back to the Home Assistant time zone",
                    time_zone,
                )
        self._attr_name = name
        self._attr_icon = icon

        if device_class:
            self._attr_device_class = device_class
        if unit_of_measurement:
            self._attr_native_unit_of_measurement = unit_of_measurement

        if state_class:
            self._attr_state_class = state_class

        # Unique ids are based on the original full sensor names so existing
        # entities (and their history) carry over to the new devices.
        self._attr_unique_id = slugify(device_id + "_" + key)
        self._attr_should_poll = False
        self._func = func
        self._attr_entity_category = entity_category
        self._ignore_zero_values = ignore_zero_values
        self._meter_interval = meter_interval

        self._attr_device_info = device_info
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
        return last_reset.astimezone(dt_util.UTC)

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

        zone_info = self._zone_info
        if zone_info is None and self.hass is not None and self.hass.config is not None:
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
