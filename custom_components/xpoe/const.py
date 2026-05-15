"""Constants for the X-PoE integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "xpoe"

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR]

DEFAULT_PORT = 443
DEFAULT_SCHEME = "https"
DEFAULT_USERNAME = "xpoeclient"
DEFAULT_PASSWORD = "xpoepass"
DEFAULT_SCAN_INTERVAL_SECONDS = 10
DEFAULT_FADE_TIME_SECONDS = 2

NUM_PORTS = 8
CHANNELS_PER_PORT = 2

EXP_SKEW_SECONDS = 60

HW_MODEL_MAP = {
    "delta": "XS-108H",
}

CONF_VERIFY_SSL = "verify_ssl"
