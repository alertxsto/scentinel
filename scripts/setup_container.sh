#!/usr/bin/env bash
# Pull the OpenFOAM solver image and check that the binaries we call exist.
#
# The image is an OpenCFD (ESI) build: it ships `simpleFoam`, not `foamRun` /
# the `incompressibleFluid` module, so that is what the case generator targets.
set -euo pipefail

IMAGE="${SCENTINEL_IMAGE:-docker.io/opencfd/openfoam-default:2512}"
FOAM_BASHRC="/usr/lib/openfoam/openfoam2512/etc/bashrc"

echo "==> Checking podman"
if ! command -v podman >/dev/null 2>&1; then
    echo "ERROR: podman is not installed" >&2
    exit 1
fi

echo "==> Pulling ${IMAGE}"
# Fully qualified on purpose: podman refuses to guess a registry when it cannot
# prompt for confirmation.
podman pull "${IMAGE}"

echo "==> Verifying the tools the pipeline uses"
podman run --rm "${IMAGE}" bash -lc "
    source ${FOAM_BASHRC}
    for tool in gmshToFoam changeDictionary simpleFoam foamToVTK; do
        command -v \$tool >/dev/null 2>&1 || { echo \"MISSING: \$tool\" >&2; exit 1; }
        echo \"  \$tool OK\"
    done
"

echo "==> Container ready"
