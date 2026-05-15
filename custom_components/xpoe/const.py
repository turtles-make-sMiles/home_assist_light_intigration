"""Constants for the X-PoE integration."""
from __future__ import annotations

DOMAIN = "xpoe"

try:
    from homeassistant.const import Platform
    PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR, Platform.BINARY_SENSOR]
except ImportError:
    # Allow this module to import outside Home Assistant (e.g. smoke tests).
    PLATFORMS = []

DEFAULT_PORT = 443
DEFAULT_SCHEME = "https"
DEFAULT_SCAN_INTERVAL_SECONDS = 10
DEFAULT_FADE_TIME_SECONDS = 2

# Where users find their switch's credentials. Surfaced in the config flow
# and the manifest.
CREDS_DOCS_URL = "https://docs.luum.io/install_guides/xs_108h_ig/"

NUM_PORTS = 8
CHANNELS_PER_PORT = 2

EXP_SKEW_SECONDS = 60

HW_MODEL_MAP = {
    "delta": "XS-108H",
}

CONF_VERIFY_SSL = "verify_ssl"
