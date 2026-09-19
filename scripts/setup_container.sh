#!/usr/bin/env bash
# Set up the OpenFOAM solver container.
#
# All of the work lives in `scentinel.core.container`, so the GUI, the CLI, and
# this script pull into exactly the same isolated storage (under
# $SCENTINEL_HOME/containers, never the user's default podman storage). This
# wrapper only checks podman and picks an interpreter.
#
# Set SCENTINEL_IMAGE to pull a different image.
set -euo pipefail

if ! command -v podman >/dev/null 2>&1; then
    echo "ERROR: podman is not installed" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

if [ -x .venv/bin/python ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

exec "${PYTHON}" -m scentinel.core.container "$@"
