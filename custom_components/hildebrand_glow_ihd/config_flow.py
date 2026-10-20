"""Config flow for Hildebrand Glow IHD MQTT."""
from __future__ import annotations

import zoneinfo
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_TIME_ZONE_ELECTRICITY,
    CONF_TIME_ZONE_GAS,
    CONF_TOPIC_PREFIX,
    DEFAULT_DEVICE_ID,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
)
from .util import normalize_device_id, normalize_topic_prefix


def _build_timezone_list() -> list[str]:
    """Return the available time zones sorted alphabetically."""

    return sorted(zoneinfo.available_timezones())


def _merge_entry_data(config_entry: ConfigEntry) -> dict[str, Any]:
    """Return a dict with options overriding data for defaults."""

    return {**config_entry.data, **config_entry.options}


class HildebrandGlowIHDMQTTConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Hildebrand Glow IHD integration."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step of the flow."""

        errors: dict[str, str] = {}
        default_device_id = normalize_device_id(
            DEFAULT_DEVICE_ID, DEFAULT_DEVICE_ID
        )

        if user_input is not None:
            device_id = normalize_device_id(
                user_input.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID), DEFAULT_DEVICE_ID
            )
            topic_prefix = normalize_topic_prefix(
                user_input.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                DEFAULT_TOPIC_PREFIX,
            )
            time_zone_electricity = user_input.get(
                CONF_TIME_ZONE_ELECTRICITY, self.hass.config.time_zone
            )
            time_zone_gas = user_input.get(
                CONF_TIME_ZONE_GAS, self.hass.config.time_zone
            )

            await self.async_set_unique_id(f"{DOMAIN}_{device_id}")
            self._abort_if_unique_id_configured()

            title = (
                f"Glow IHD ({device_id})"
                if device_id and device_id != default_device_id
                else "Hildebrand Glow IHD"
            )

            return self.async_create_entry(
                title=title,
                data={
                    CONF_DEVICE_ID: device_id,
                    CONF_TOPIC_PREFIX: topic_prefix,
                    CONF_TIME_ZONE_ELECTRICITY: time_zone_electricity,
                    CONF_TIME_ZONE_GAS: time_zone_gas,
                },
            )

        get_timezones: list[str] = await self.hass.async_add_executor_job(
            _build_timezone_list
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_ID,
                        default=default_device_id,
                    ): str,
                    vol.Required(
                        CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX
                    ): str,
                    vol.Required(
                        CONF_TIME_ZONE_ELECTRICITY,
                        default=self.hass.config.time_zone,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=get_timezones,
                            mode=SelectSelectorMode.DROPDOWN,
                            sort=True,
                        )
                    ),
                    vol.Required(
                        CONF_TIME_ZONE_GAS, default=self.hass.config.time_zone
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=get_timezones,
                            mode=SelectSelectorMode.DROPDOWN,
                            sort=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow for this handler."""

        return HildebrandGlowIHDMQTTOptionsFlowHandler()


class HildebrandGlowIHDMQTTOptionsFlowHandler(OptionsFlowWithReload):
    """Handle options flow for Hildebrand Glow IHD MQTT."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle options flow."""

        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = normalize_device_id(
                user_input.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID), DEFAULT_DEVICE_ID
            )
            unique_id = f"{DOMAIN}_{device_id}"
            if any(
                entry.unique_id == unique_id
                and entry.entry_id != self.config_entry.entry_id
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            ):
                errors[CONF_DEVICE_ID] = "already_configured"

        if user_input is not None and not errors:
            return self.async_create_entry(
                title="",
                data={
                    CONF_DEVICE_ID: device_id,
                    CONF_TOPIC_PREFIX: normalize_topic_prefix(
                        user_input.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                        DEFAULT_TOPIC_PREFIX,
                    ),
                    CONF_TIME_ZONE_ELECTRICITY: user_input.get(
                        CONF_TIME_ZONE_ELECTRICITY, self.hass.config.time_zone
                    ),
                    CONF_TIME_ZONE_GAS: user_input.get(
                        CONF_TIME_ZONE_GAS, self.hass.config.time_zone
                    ),
                },
            )

        get_timezones: list[str] = await self.hass.async_add_executor_job(
            _build_timezone_list
        )

        # Re-show the values just submitted when the form has errors
        current_config = {**_merge_entry_data(self.config_entry), **(user_input or {})}
        current_device_id = normalize_device_id(
            current_config.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID), DEFAULT_DEVICE_ID
        )
        current_topic_prefix = normalize_topic_prefix(
            current_config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
            DEFAULT_TOPIC_PREFIX,
        )
        current_time_zone_electricity = current_config.get(
            CONF_TIME_ZONE_ELECTRICITY, self.hass.config.time_zone
        )
        current_time_zone_gas = current_config.get(
            CONF_TIME_ZONE_GAS, self.hass.config.time_zone
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_ID,
                    default=current_device_id,
                ): str,
                vol.Required(
                    CONF_TOPIC_PREFIX,
                    default=current_topic_prefix,
                ): str,
                vol.Required(
                    CONF_TIME_ZONE_ELECTRICITY,
                    default=current_time_zone_electricity,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=get_timezones,
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=True,
                    )
                ),
                vol.Required(
                    CONF_TIME_ZONE_GAS,
                    default=current_time_zone_gas,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=get_timezones,
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=data_schema, errors=errors
        )
