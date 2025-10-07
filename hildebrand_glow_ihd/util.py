"""Utility helpers for the Hildebrand Glow IHD integration."""
from __future__ import annotations


def normalize_device_id(device_id: str | None, default: str = "") -> str:
    """Return the device id formatted for use by the integration."""

    if not device_id:
        return default
    return device_id.strip().upper().replace(":", "").replace(" ", "") or default


def normalize_topic_prefix(topic_prefix: str | None, default: str) -> str:
    """Return the MQTT topic prefix stripped of unsupported characters."""

    if not topic_prefix:
        return default
    cleaned_prefix = topic_prefix.strip().replace("#", "").replace(" ", "")
    return cleaned_prefix or default
