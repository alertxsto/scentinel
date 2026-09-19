#!/usr/bin/env bash
# Build amd64 .deb, .rpm, and an Arch-style prefix .tar.gz under dist/packages/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

VERSION="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
echo "==> packaging scentinel ${VERSION}"

STAGE="${ROOT}/build/linux-root"
OUT="${ROOT}/dist/packages"
export STAGE
rm -rf "${STAGE}" "${OUT}"
mkdir -p "${STAGE}/opt" "${STAGE}/usr/bin" "${STAGE}/usr/share/applications" \
  "${STAGE}/usr/share/doc/scentinel" "${OUT}" "${ROOT}/build"

PYTHON="${PYTHON:-python3}"
"${PYTHON}" -m pip install --upgrade pip build
"${PYTHON}" -m build --wheel --outdir "${ROOT}/dist"

WHEEL="$(ls -1 "${ROOT}/dist"/scentinel-*.whl | tail -1)"
"${PYTHON}" -m venv "${STAGE}/opt/scentinel"
"${STAGE}/opt/scentinel/bin/pip" install --upgrade pip
"${STAGE}/opt/scentinel/bin/pip" install "${WHEEL}[cfd,report]"

python3 - <<'PY'
from pathlib import Path
import os

root = Path(os.environ["STAGE"]) / "opt" / "scentinel"
for path in (root / "bin").iterdir():
    try:
        data = path.read_bytes()
    except OSError:
        continue
    if not data.startswith(b"#!"):
        continue
    first, _, rest = data.partition(b"\n")
    if b"bin/python" in first:
        path.write_bytes(b"#!/opt/scentinel/bin/python3\n" + rest)
cfg = root / "pyvenv.cfg"
if cfg.exists():
    lines = [
        line
        for line in cfg.read_text().splitlines()
        if not line.startswith("home =") and not line.startswith("command =")
    ]
    lines.append("home = /opt/scentinel/bin")
    cfg.write_text("\n".join(lines) + "\n")
PY

install -m 0755 "${ROOT}/packaging/scentinel.wrapper" "${STAGE}/usr/bin/scentinel"
install -m 0644 "${ROOT}/packaging/scentinel.desktop" "${STAGE}/usr/share/applications/scentinel.desktop"
install -m 0644 "${ROOT}/LICENSE" "${STAGE}/usr/share/doc/scentinel/LICENSE"
sed "s/^pkgver=.*/pkgver=${VERSION}/" "${ROOT}/packaging/arch/PKGBUILD" > "${OUT}/PKGBUILD"

tar -C "${STAGE}" -czf "${OUT}/scentinel-${VERSION}-x86_64.tar.gz" opt usr

NFPM_VERSION="2.47.0"
curl -fsSL "https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz" \
  -o "${ROOT}/build/nfpm.tgz"
gzip -t "${ROOT}/build/nfpm.tgz"
tar -C "${ROOT}/build" -xzf "${ROOT}/build/nfpm.tgz" nfpm

cat > "${ROOT}/build/nfpm.yaml" <<EOF
name: scentinel
arch: amd64
platform: linux
version: ${VERSION}
release: "1"
section: science
priority: optional
maintainer: Scentinel <https://github.com/alertxsto/scentinel>
description: CFD simulation studio for gas sensor placement in waste collection vehicles
license: MIT
homepage: https://github.com/alertxsto/scentinel
recommends:
  - podman
contents:
  - src: ${STAGE}/opt/scentinel
    dst: /opt/scentinel
  - src: ${STAGE}/usr/bin/scentinel
    dst: /usr/bin/scentinel
    file_info:
      mode: 0755
  - src: ${STAGE}/usr/share/applications/scentinel.desktop
    dst: /usr/share/applications/scentinel.desktop
  - src: ${STAGE}/usr/share/doc/scentinel/LICENSE
    dst: /usr/share/doc/scentinel/LICENSE
EOF

"${ROOT}/build/nfpm" package -f "${ROOT}/build/nfpm.yaml" -p deb -t "${OUT}"
"${ROOT}/build/nfpm" package -f "${ROOT}/build/nfpm.yaml" -p rpm -t "${OUT}"

ls -lh "${OUT}"
