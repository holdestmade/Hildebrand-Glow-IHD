"""Setup for the Hildebrand Glow IHD MQTT integration."""
from __future__ import annotations

import logging
from typing import Any

from awesomeversion.awesomeversion import AwesomeVersion
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, __version__ as HA_VERSION, CONF_DEVICE_ID  # noqa: N812
from homeassistant.core import HomeAssistant

from .const import (
    CONF_GAS_UNITS,
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DEFAULT_DEVICE_ID,
    DEFAULT_GAS_UNITS,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    MIN_HA_VERSION,
)
from .util import normalize_device_id, normalize_topic_prefix

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Hildebrand Glow IHD MQTT integration."""

    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):  # pragma: no cover
        msg = (
            "This integration requires at least HomeAssistant version "
            f" {MIN_HA_VERSION}, you are running version {HA_VERSION}."
            " Please upgrade HomeAssistant to continue use of this integration."
        )
        _LOGGER.critical(msg)
        return False

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Hildebrand Glow IHD MQTT config entry."""

    _LOGGER.debug("Setting up Hildebrand Glow IHD MQTT integration")

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {}

    entry_data = hass.data[DOMAIN][entry.entry_id]

    # Merge options over data so that options always win
    merged_entry: dict[str, Any] = {**entry.data, **entry.options}

    raw_device_id = merged_entry.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)
    entry_data[CONF_DEVICE_ID] = normalize_device_id(
        raw_device_id, DEFAULT_DEVICE_ID
    )

    raw_topic_prefix = merged_entry.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    entry_data[CONF_TOPIC_PREFIX] = normalize_topic_prefix(
        raw_topic_prefix, DEFAULT_TOPIC_PREFIX
    )

    entry_data[CONF_TIME_ZONE_ELECTRICITY] = merged_entry.get(
        CONF_TIME_ZONE_ELECTRICITY, hass.config.time_zone
    )
    entry_data[CONF_TIME_ZONE_GAS] = merged_entry.get(
        CONF_TIME_ZONE_GAS, hass.config.time_zone
    )
    entry_data[CONF_GAS_UNITS] = merged_entry.get(
        CONF_GAS_UNITS, DEFAULT_GAS_UNITS
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.debug("Finished setting up Hildebrand Glow IHD MQTT integration")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Hildebrand Glow IHD MQTT config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry reload requests when options change."""

    await hass.config_entries.async_reload(entry.entry_id)
