#!/bin/sh
set -eu

# Build a Prime 2 / JC16 variant of audioshim without modifying the Prime GO
# source file.  This is intentionally a minimal first-port patch:
#   hw:1,0  / S24_LE  ->  hw:JC16,0 / S32_LE
# Everything else (4ch interleave, 44.1 kHz, pacing/stubs) stays identical.
#
# Usage:
#   RX3=/path/to/extracted/XDJRX3-rootfs ./build-jc16-audioshim.sh
# Optional:
#   CROSS=arm-linux-gnueabi- OUT=audioshim-jc16.so ./build-jc16-audioshim.sh

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC="$HERE/audioshim.c"
RX3=${RX3:-"$HERE/../../extracted/XDJRX3-rootfs"}
CROSS=${CROSS:-arm-linux-gnueabi-}
CC=${CC:-${CROSS}gcc}
OUT=${OUT:-"$HERE/audioshim-jc16.so"}

if [ ! -f "$SRC" ]; then
    echo "error: missing $SRC" >&2
    exit 1
fi
if [ ! -f "$RX3/lib/libdl.so.2" ]; then
    echo "error: RX3 rootfs not found at $RX3" >&2
    echo "set RX3=/path/to/extracted/XDJRX3-rootfs" >&2
    exit 1
fi
if ! command -v "$CC" >/dev/null 2>&1; then
    echo "error: compiler not found: $CC" >&2
    exit 1
fi

TMP=$(mktemp "${TMPDIR:-/tmp}/audioshim-jc16.XXXXXX.c")
trap 'rm -f "$TMP"' EXIT HUP INT TERM
cp "$SRC" "$TMP"

# ALSA enum value: S32_LE = 10.  audioshim intentionally avoids ALSA headers
# because it is linked against the old RX3 userspace ABI.
sed -i '/#define SND_PCM_FORMAT_S24_LE   6/a #define SND_PCM_FORMAT_S32_LE   10' "$TMP"

# The named card is stable on JC16 even if USB MIDI/display cards change index.
sed -i 's/"hw:1,0"/"hw:JC16,0"/g' "$TMP"

# The Prime 2 codec was measured live as S32_LE / 4ch / 44100 Hz.
sed -i 's/real_snd_pcm_hw_params_set_format(g_real_playback, params, SND_PCM_FORMAT_S24_LE)/real_snd_pcm_hw_params_set_format(g_real_playback, params, SND_PCM_FORMAT_S32_LE)/' "$TMP"
sed -i 's/real set_format(S24_LE=6)/real set_format(S32_LE=10)/' "$TMP"

# If rbp asks for a control device by the real target name, allow ALSA to open it.
sed -i 's/strstr(name, "hw:1") || /strstr(name, "hw:JC16") || strstr(name, "hw:1") || /' "$TMP"

# Sanity checks: fail rather than silently producing a Prime GO binary.
grep -q '#define SND_PCM_FORMAT_S32_LE   10' "$TMP"
grep -q '"hw:JC16,0"' "$TMP"
grep -q 'SND_PCM_FORMAT_S32_LE)' "$TMP"

"$CC" \
    -O2 -march=armv5t -mfloat-abi=soft -fno-stack-protector -fPIC \
    -Wall -Wextra -Wno-unused-parameter \
    -shared -o "$OUT" "$TMP" \
    "$RX3/lib/libdl.so.2" -lc \
    -L"$RX3/lib" -L"$RX3/usr/lib" \
    -Wl,-rpath-link,"$RX3/lib:$RX3/usr/lib"

if command -v "${CROSS}readelf" >/dev/null 2>&1; then
    if "${CROSS}readelf" -A "$OUT" | grep -qi 'Tag_ABI_VFP_args'; then
        echo "error: built object has hard-float ABI tag" >&2
        rm -f "$OUT"
        exit 1
    fi
fi

echo "built: $OUT"
echo "target: JC16 / hw:JC16,0 / S32_LE / 44100 Hz / 4ch"
