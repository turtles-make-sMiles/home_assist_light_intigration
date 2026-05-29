#!/usr/bin/env bash
# Install / update the X-PoE Home Assistant integration.
#
# Run from inside your Home Assistant `config/custom_components/` directory:
#
#   cd /path/to/homeassistant/config/custom_components
#   curl -fsSL https://api.bitbucket.org/2.0/repositories/amatiscontrols/home_assist_light_intigration/src/main/install.sh | bash
#
# Note: use the api.bitbucket.org /src/main/ URL, not the browser /raw/main/ URL —
# the raw URL 404s for anonymous curl even on public repos.
#
# Pin a specific tag or branch:
#   curl ... | XPOE_REF=v0.1.0 bash
#
# Then restart Home Assistant and add the integration via the UI.

set -euo pipefail

WORKSPACE="amatiscontrols"
REPO="home_assist_light_intigration"
TARGET_NAME="xpoe"
REF="${XPOE_REF:-main}"
ARCHIVE_URL="https://bitbucket.org/${WORKSPACE}/${REPO}/get/${REF}.tar.gz"

err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

if [[ "$(basename "$PWD")" != "custom_components" ]]; then
    err "must be run from a 'custom_components' directory (got '$(basename "$PWD")').
Try:  cd /path/to/homeassistant/config/custom_components  &&  re-run."
fi

DOWNLOAD=""
if command -v curl >/dev/null 2>&1; then
    DOWNLOAD="curl -fsSL"
elif command -v wget >/dev/null 2>&1; then
    DOWNLOAD="wget -qO-"
else
    err "need curl or wget on PATH"
fi
command -v tar >/dev/null 2>&1 || err "need tar on PATH"

if [[ -e "${TARGET_NAME}" ]]; then
    BACKUP="${TARGET_NAME}.bak.$(date +%Y%m%d-%H%M%S)"
    info "Backing up existing ./${TARGET_NAME} -> ./${BACKUP}"
    mv "${TARGET_NAME}" "${BACKUP}"
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

info "Downloading ${ARCHIVE_URL}"
${DOWNLOAD} "${ARCHIVE_URL}" | tar -xz -C "${TMPDIR}"

EXTRACTED="$(find "${TMPDIR}" -maxdepth 1 -mindepth 1 -type d | head -n1)"
[[ -n "${EXTRACTED}" ]] || err "archive empty or malformed"

SRC="${EXTRACTED}/custom_components/${TARGET_NAME}"
[[ -d "${SRC}" ]] || err "${TARGET_NAME} not found in archive at ${SRC#${TMPDIR}/}"

mv "${SRC}" "./${TARGET_NAME}"

VERSION=""
if [[ -f "./${TARGET_NAME}/manifest.json" ]]; then
    VERSION="$(grep -E '"version"' "./${TARGET_NAME}/manifest.json" | head -n1 \
        | sed -E 's/.*"version":[[:space:]]*"([^"]+)".*/\1/')"
fi

info "Installed: $PWD/${TARGET_NAME}${VERSION:+ (v${VERSION})}"
info ""
info "Next:"
info "  1. Restart Home Assistant."
info "  2. Settings -> Devices & Services -> Add Integration -> 'X-PoE'."
