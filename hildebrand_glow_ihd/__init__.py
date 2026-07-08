"""Setup for the Hildebrand Glow IHD MQTT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
)
from .util import normalize_device_id, normalize_topic_prefix

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@callback
def _async_cleanup_stale_devices(
    hass: HomeAssistant, entry: ConfigEntry, device_mac: str
) -> None:
    """Remove entities and devices left over from a previously configured device id."""

    if device_mac == DEFAULT_DEVICE_ID:
        return

    entity_registry = er.async_get(hass)
    unique_id_prefix = f"{slugify(device_mac)}_"
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if not entity.unique_id.startswith(unique_id_prefix):
            _LOGGER.debug("Removing stale entity %s", entity.entity_id)
            entity_registry.async_remove(entity.entity_id)

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not er.async_entries_for_device(
            entity_registry, device.id, include_disabled_entities=True
        ):
            _LOGGER.debug("Removing stale device %s", device.name)
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Hildebrand Glow IHD MQTT config entry."""

    _LOGGER.debug("Setting up Hildebrand Glow IHD MQTT integration")

    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT integration is not available")

    entry_data = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})

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

    # Keep the entry unique id in sync when the device id is changed via options
    expected_unique_id = f"{DOMAIN}_{entry_data[CONF_DEVICE_ID]}"
    if entry.unique_id != expected_unique_id:
        hass.config_entries.async_update_entry(entry, unique_id=expected_unique_id)

    _async_cleanup_stale_devices(hass, entry, entry_data[CONF_DEVICE_ID])

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
