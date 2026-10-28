# Hildebrand Glow IHD MQTT Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/holdestmade/Hildebrand-Glow-IHD/actions/workflows/validate.yml/badge.svg)](https://github.com/holdestmade/Hildebrand-Glow-IHD/actions/workflows/validate.yml)

This repository contains a custom [Home Assistant](https://www.home-assistant.io/) integration that exposes the telemetry published by a Hildebrand Glow In-Home Display (IHD) over MQTT.  It parses the topics emitted by the Glow IHD and creates Home Assistant sensors for electricity and gas consumption, device status, and supporting metadata.

## Features

- Native Home Assistant config flow for setting up the integration from the UI.
- Supports customising the MQTT topic prefix, device ID, and per-fuel time zones.
- Handles both electricity and gas metrics, with gas reported in both kWh and m³.
- Depends on the core MQTT integration and listens for locally published updates (`iot_class: local_push`).

## Devices

Each Glow IHD is split into three devices:

| Device | Entities |
| --- | --- |
| **Smart Meter IHD** | Software version, hardware, last seen, HAN status, RSSI and LQI |
| **Smart Meter Electricity** | Import/export energy, power, unit rate, standing charge and cost |
| **Smart Meter Gas** | Import energy and volume, unit rate, standing charge and cost |

The electricity and gas meters are linked to the IHD as devices connected *via* it, since they are separate meters that report through the IHD's Zigbee HAN.

### Upgrading from 2.x

Entity unique ids are unchanged, so existing entities, their history and Energy dashboard statistics carry over. The existing device becomes **Smart Meter IHD** and the meter entities move to the new electricity and gas devices. Entity ids are kept; only the friendly names change slightly (for example `Smart Meter Electricity: Import` becomes `Smart Meter Electricity Import`).

## Installation

### HACS (recommended)

This integration is not in the HACS default store, so add it as a custom repository:

1. Make sure [HACS](https://hacs.xyz/docs/use/) is installed in your Home Assistant instance.
2. In Home Assistant, open **HACS**, then select the **⋮** menu in the top-right corner and choose **Custom repositories**.
3. Enter `https://github.com/holdestmade/Hildebrand-Glow-IHD` as the repository and select **Integration** as the type, then select **Add**.
4. Search HACS for **Hildebrand Glow IHD MQTT**, open it and select **Download**.
5. Restart Home Assistant.

Or use this button to open the repository in HACS directly:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=holdestmade&repository=Hildebrand-Glow-IHD&category=integration)

Updates are offered through HACS whenever a new release is published.

### Manual

1. Download this repository.
2. Copy the `custom_components/hildebrand_glow_ihd` directory into the `custom_components` folder of your Home Assistant configuration directory (create the folder if it does not exist).
3. Restart Home Assistant.

## Configuration

1. Ensure the MQTT integration is configured and receiving messages from your Glow IHD.
2. In Home Assistant, go to **Settings → Devices & Services → Add Integration**.
3. Search for **Hildebrand Glow IHD MQTT** and follow the on-screen prompts.
4. Provide the Glow device ID (defaults to `+` for broadcast), the MQTT topic prefix (defaults to `glow`), and select appropriate time zones for electricity and gas data.

These settings can be changed later from the integration's **Configure** button.

## Requirements

- Home Assistant 2026.8.0 or newer.
- An operational MQTT broker receiving Glow IHD telemetry.

For issues or feature requests, please use the [GitHub issue tracker](https://github.com/holdestmade/Hildebrand-Glow-IHD/issues).

## License

Released under the [MIT License](LICENSE). Originally based on [megakid/ha_hildebrand_glow_ihd_mqtt](https://github.com/megakid/ha_hildebrand_glow_ihd_mqtt).
