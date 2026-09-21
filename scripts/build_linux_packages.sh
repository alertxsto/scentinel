#!/usr/bin/env bash
# Build amd64 .deb, .rpm, and an Arch-style prefix .tar.gz under dist/packages/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

VERSION="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
echo "==> packaging scentinel ${VERSION}"

STAGE="${ROOT}/build/linux-root"
BUILD_ENV="${ROOT}/build/linux-package-venv"
OUT="${ROOT}/dist/packages"
rm -rf "${STAGE}" "${BUILD_ENV}" "${OUT}" "${ROOT}/dist/scentinel"
mkdir -p "${STAGE}/opt/scentinel" "${STAGE}/usr/bin" \
  "${STAGE}/usr/share/applications" "${STAGE}/usr/share/doc/scentinel" \
  "${OUT}" "${ROOT}/build"

PYTHON="${PYTHON:-python3}"
"${PYTHON}" -m venv "${BUILD_ENV}"
"${BUILD_ENV}/bin/pip" install --upgrade pip build pyinstaller
"${BUILD_ENV}/bin/python" -m build --wheel --outdir "${ROOT}/dist"

WHEEL="$(ls -1 "${ROOT}/dist"/scentinel-*.whl | tail -1)"
"${BUILD_ENV}/bin/pip" install "${WHEEL}[cfd,report]"
"${BUILD_ENV}/bin/python" -m PyInstaller \
  --noconfirm --clean "${ROOT}/packaging/scentinel-linux.spec"
cp -a "${ROOT}/dist/scentinel/." "${STAGE}/opt/scentinel/"

echo "==> smoke-testing bundled runtime"
QT_QPA_PLATFORM=offscreen \
  "${STAGE}/opt/scentinel/scentinel" --package-smoke-test

install -m 0755 "${ROOT}/packaging/scentinel.wrapper" "${STAGE}/usr/bin/scentinel"
install -m 0644 "${ROOT}/packaging/scentinel.desktop" "${STAGE}/usr/share/applications/scentinel.desktop"
install -m 0644 "${ROOT}/LICENSE" "${STAGE}/usr/share/doc/scentinel/LICENSE"
install -m 0644 "${ROOT}/CHANGELOG.md" "${STAGE}/usr/share/doc/scentinel/CHANGELOG.md"
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
  - src: ${STAGE}/usr/share/doc/scentinel/CHANGELOG.md
    dst: /usr/share/doc/scentinel/CHANGELOG.md
EOF

"${ROOT}/build/nfpm" package -f "${ROOT}/build/nfpm.yaml" -p deb -t "${OUT}"
"${ROOT}/build/nfpm" package -f "${ROOT}/build/nfpm.yaml" -p rpm -t "${OUT}"

ls -lh "${OUT}"
