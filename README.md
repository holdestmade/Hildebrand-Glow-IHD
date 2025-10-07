# Hildebrand Glow IHD MQTT Home Assistant Integration

This repository contains a custom [Home Assistant](https://www.home-assistant.io/) integration that exposes the telemetry published by a Hildebrand Glow In-Home Display (IHD) over MQTT.  It parses the topics emitted by the Glow IHD and creates Home Assistant sensors for electricity and gas consumption, device status, and supporting metadata.

## Features

- Native Home Assistant config flow for setting up the integration from the UI.
- Supports customising the MQTT topic prefix, device ID, and per-fuel time zones.
- Handles both electricity and gas metrics, including configurable gas units (kWh or m³).
- Depends on the core MQTT integration and listens for locally published updates (`iot_class: local_push`).

## Installation

1. Copy the `hildebrand_glow_ihd` directory into your Home Assistant `custom_components` folder.
2. Restart Home Assistant to load the integration.

## Configuration

1. Ensure the MQTT integration is configured and receiving messages from your Glow IHD.
2. In Home Assistant, go to **Settings → Devices & Services → Add Integration**.
3. Search for **Hildebrand Glow IHD MQTT** and follow the on-screen prompts.
4. Provide the Glow device ID (defaults to `+` for broadcast), the MQTT topic prefix (defaults to `glow`), select appropriate time zones for electricity and gas data, and choose the desired gas units.

## Requirements

- Home Assistant 2025.10.0 or newer.
- An operational MQTT broker receiving Glow IHD telemetry.

For issues or feature requests, please use the [GitHub issue tracker](https://github.com/megakid/ha_hildebrand_glow_ihd_mqtt/issues).
