#!/bin/bash
set -euo pipefail
BUILD_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
PREFIX="$BUILD_ROOT/build-sources/audio-libs"
mkdir -p "$PREFIX"
cd "$BUILD_ROOT/build-sources/lame-3.100"
./configure --prefix="$PREFIX" --build=aarch64-apple-darwin --host=aarch64-apple-darwin --disable-shared --enable-static --disable-frontend --with-pic CFLAGS="-O2 -mmacosx-version-min=13.5"
make -j6
make install
cd "$BUILD_ROOT/build-sources/ffmpeg-7.1"
./configure --prefix="$PREFIX" --arch=arm64 --cc=clang --cxx=clang++ --disable-autodetect --disable-everything --disable-doc --disable-debug --disable-programs --enable-ffmpeg --enable-avcodec --enable-avformat --enable-avutil --enable-swresample --enable-avfilter --enable-libmp3lame --enable-decoder=aac,aac_fixed,opus,vorbis,mp3,mp3float,flac,pcm_s16le,pcm_s24le,pcm_f32le --enable-parser=aac,aac_latm,mpegaudio,flac,opus,vorbis --enable-demuxer=mov,matroska,mp3,wav,ogg,flac,aac --enable-muxer=mp3,wav --enable-encoder=libmp3lame,pcm_s16le --enable-protocol=file,pipe --enable-filter=aformat,anull,aresample,volume,atrim,asetpts,afade,concat --extra-cflags="-mmacosx-version-min=13.5 -I$PREFIX/include" --extra-ldflags="-mmacosx-version-min=13.5 -L$PREFIX/lib"
make -j6
cp ffmpeg "$BUILD_ROOT/tools/ffmpeg"
cp COPYING.LGPLv2.1 "$BUILD_ROOT/licenses/FFmpeg-LGPL-2.1.txt"
cp "$BUILD_ROOT/build-sources/lame-3.100/COPYING" "$BUILD_ROOT/licenses/LAME-LGPL-2.0.txt"
