#!/usr/bin/env bash
set -euo pipefail
BUILD_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$BUILD_ROOT"
PREFIX="$BUILD_ROOT/build-sources/audio-libs"
mkdir -p "$PREFIX" tools
tar -xJf build-sources/ffmpeg-7.1.tar.xz -C build-sources
tar -xzf build-sources/lame-3.100.tar.gz -C build-sources
cd build-sources/lame-3.100
./configure --prefix="$PREFIX" --host=x86_64-w64-mingw32 --disable-shared --enable-static --disable-frontend CFLAGS="-O2" LDFLAGS="-static"
make -j4
make install
cd "$BUILD_ROOT/build-sources/ffmpeg-7.1"
./configure --prefix="$PREFIX" --arch=x86_64 --target-os=mingw32 --cc=gcc --cxx=g++ --disable-shared --enable-static --disable-autodetect --disable-everything --disable-doc --disable-debug --disable-programs --enable-ffmpeg --enable-avcodec --enable-avformat --enable-avutil --enable-swresample --enable-avfilter --enable-libmp3lame --enable-decoder=aac,aac_fixed,opus,vorbis,mp3,mp3float,flac,pcm_s16le,pcm_s24le,pcm_f32le --enable-parser=aac,aac_latm,mpegaudio,flac,opus,vorbis --enable-demuxer=mov,matroska,mp3,wav,ogg,flac,aac --enable-muxer=mp3,wav --enable-encoder=libmp3lame,pcm_s16le --enable-protocol=file,pipe --enable-filter=aformat,anull,aresample,volume,atrim,asetpts,afade,concat --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib -static -static-libgcc"
make -j4
cp ffmpeg.exe "$BUILD_ROOT/tools/ffmpeg.exe"
cp COPYING.LGPLv2.1 "$BUILD_ROOT/licenses/FFmpeg-LGPL-2.1.txt"
cp "$BUILD_ROOT/build-sources/lame-3.100/COPYING" "$BUILD_ROOT/licenses/LAME-LGPL-2.0.txt"
# A portable executable may import Windows system DLLs, never MSYS2 runtime DLLs.
objdump -p "$BUILD_ROOT/tools/ffmpeg.exe" > "$BUILD_ROOT/verification/ffmpeg-pe-imports.txt"
if grep -Eqi 'DLL Name:.*(msys|libgcc|libstdc|libwinpthread|libmp3lame)' "$BUILD_ROOT/verification/ffmpeg-pe-imports.txt"; then
    printf '%s\n' 'FFmpeg requires a non-system DLL; aborting portable build.' >&2
    exit 1
fi
