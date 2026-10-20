from typing import Final
from enum import Enum

DOMAIN: Final = "hildebrand_glow_ihd"

CONF_TIME_ZONE_ELECTRICITY = "time_zone_electricity"
CONF_TIME_ZONE_GAS = "time_zone_gas"
CONF_TOPIC_PREFIX = "topic_prefix"

DEFAULT_DEVICE_ID = "+"
DEFAULT_TOPIC_PREFIX = "glow"


# Meter intervals
class MeterInterval(Enum):
    """Meter intervals."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
