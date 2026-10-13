#!/bin/bash
set -euo pipefail
BUILD_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$BUILD_ROOT"
if [ "$(uname -m)" != "arm64" ]; then
    printf '%s\n' 'Esta compilación requiere macOS con Apple Silicon.' >&2
    exit 1
fi
PYTHON_EXECUTABLE="${AUDIOLOCAL_BUILD_PYTHON:-python3}"
"$PYTHON_EXECUTABLE" -c 'import sys, tkinter; assert sys.version_info >= (3, 10)'
"$PYTHON_EXECUTABLE" -m venv .build-venv
.build-venv/bin/python3 -m pip --disable-pip-version-check --no-cache-dir install -r requirements-build.txt
mkdir -p tools verification build-sources licenses
curl --fail --location https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp_macos --output tools/yt-dlp_macos
curl --fail --location https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/SHA2-256SUMS --output verification/yt-dlp-SHA2-256SUMS
(cd tools && sed -n '/  yt-dlp_macos$/p' ../verification/yt-dlp-SHA2-256SUMS | shasum -a 256 -c -)
curl --fail --location https://nodejs.org/dist/v24.14.1/node-v24.14.1-darwin-arm64.tar.xz --output build-sources/node-v24.14.1-darwin-arm64.tar.xz
curl --fail --location https://nodejs.org/dist/v24.14.1/SHASUMS256.txt --output verification/Node-SHASUMS256.txt
(cd build-sources && sed -n '/  node-v24.14.1-darwin-arm64.tar.xz$/p' ../verification/Node-SHASUMS256.txt | shasum -a 256 -c -)
tar -xJf build-sources/node-v24.14.1-darwin-arm64.tar.xz -C build-sources
cp build-sources/node-v24.14.1-darwin-arm64/bin/node tools/node
if [ ! -f build-sources/ffmpeg-7.1.tar.xz ]; then
    curl --fail --location https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz --output build-sources/ffmpeg-7.1.tar.xz
fi
if [ ! -f build-sources/lame-3.100.tar.gz ]; then
    curl --fail --location https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz --output build-sources/lame-3.100.tar.gz
fi
tar -xJf build-sources/ffmpeg-7.1.tar.xz -C build-sources
tar -xzf build-sources/lame-3.100.tar.gz -C build-sources
bash build-ffmpeg.sh
chmod +x tools/ffmpeg tools/node tools/yt-dlp_macos
PYINSTALLER_CONFIG_DIR="$BUILD_ROOT/.pyinstaller-cache" .build-venv/bin/python3 -m PyInstaller --noconfirm --distpath dist --workpath build AudioLocal.spec
printf '%s\n' 'Lista: dist/AudioLocal.app'
