#!/bin/sh
set -eu

# PrimeBox launcher for Denon Prime 2 / JC16.
# This intentionally mirrors start-rb.sh but selects the JC16 audioshim.
# Runtime changes remain under /data; Engine OS is restored by stop-rb-jc16.sh.

AUDIO_SHIM=/data/audioshim-jc16.so
CHROOT=/data/rbx3-run
STOP=/data/stop-rb-jc16.sh
ENGINE_STOPPED=0

cleanup() {
    rc=$?
    trap - EXIT HUP INT TERM
    if [ "$ENGINE_STOPPED" = 1 ]; then
        echo "rolling back to Engine OS..." >&2
        sh "$STOP" || rc=1
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
fail() { echo "ERROR: $*" >&2; exit 1; }

# Refuse to touch services on anything other than the validated Prime 2 ID.
COMPAT="$(tr '\000' ' ' </proc/device-tree/compatible 2>/dev/null || true)"
case "$COMPAT" in
    *inmusic,jc16*) ;;
    *) fail "this launcher is for Denon Prime 2 / JC16 only (compatible='$COMPAT')" ;;
esac

# Hardware preflight before Engine OS is stopped.
grep -q 'JC16' /proc/asound/cards 2>/dev/null || fail "ALSA card JC16 not found"
[ -e /dev/fb0 ] || fail "/dev/fb0 not found"
[ -e /dev/input/event0 ] || fail "/dev/input/event0 not found"
[ -e /dev/snd/seq ] || fail "/dev/snd/seq not found"

# Payload/chroot preflight before Engine OS is stopped.
for f in \
    "$AUDIO_SHIM" \
    /data/rbp-audio \
    /data/knobshim2.so \
    /data/fbshim-tsc.so \
    /data/libdirectfb_fbdev-rot16.so \
    /data/fix-dev.sh \
    /data/usb-watch.sh \
    "$STOP" \
    /data/jc16-runtime.sh \
    "$CHROOT/lib/ld-linux.so.3" \
    "$CHROOT/usr/bin/edb_streamd"; do
    [ -e "$f" ] || fail "missing required file: $f"
done
mkdir -p "$CHROOT/root/pdj" "$CHROOT/usr/lib" "$CHROOT/usr/lib/directfb-1.4-0/systems"

. /data/jc16-runtime.sh

# 1. Release hardware currently owned by Engine OS.
ENGINE_STOPPED=1
systemctl stop engine.service edisksd.service || fail "could not stop Engine services"
sleep 1

# 2. Kill stale PrimeBox processes only.
for p in $(primebox_pids); do kill "$p" 2>/dev/null || true; done
sleep 2
for p in $(primebox_pids); do kill -9 "$p" 2>/dev/null || true; done
sleep 1
[ -z "$(primebox_pids)" ] || fail "stale PrimeBox process still running"

# 3. Setup device binds/stubs used by the RX3 userspace.
sh /data/fix-dev.sh || fail "fix-dev.sh failed"

# 4. Deploy rbp and shims into the chroot.
cp /data/rbp-audio "$CHROOT/root/pdj/rbp"
chmod 755 "$CHROOT/root/pdj/rbp"

cp /data/knobshim2.so "$CHROOT/root/pdj/knobshim.so"
cp /data/knobshim2.so "$CHROOT/usr/lib/knobshim.so"
chmod 755 "$CHROOT/usr/lib/knobshim.so" "$CHROOT/root/pdj/knobshim.so"

cp "$AUDIO_SHIM" "$CHROOT/root/pdj/audioshim.so"
cp "$AUDIO_SHIM" "$CHROOT/usr/lib/audioshim.so"
chmod 755 "$CHROOT/usr/lib/audioshim.so" "$CHROOT/root/pdj/audioshim.so"

cp /data/fbshim-tsc.so "$CHROOT/root/pdj/fbshim.so"
cp /data/fbshim-tsc.so "$CHROOT/usr/lib/fbshim.so"
chmod 755 "$CHROOT/usr/lib/fbshim.so" "$CHROOT/root/pdj/fbshim.so"

cp /data/libdirectfb_fbdev-rot16.so "$CHROOT/usr/lib/directfb-1.4-0/systems/libdirectfb_fbdev.so"
chmod 755 "$CHROOT/usr/lib/directfb-1.4-0/systems/libdirectfb_fbdev.so"

# 5. Clean stale IPC/logs.
rm -f /tmp/guard_LocalDBServer /tmp/req_LocalDBServer \
      /tmp/knobshim.log /tmp/audioshim.log /tmp/dfbdig*.log \
      /tmp/rot_surface.dump /data/rbp-p.log

# 6. Start DeviceSQL daemon inside the chroot.
export EDB_BIN=/usr/bin
nohup chroot "$CHROOT" /lib/ld-linux.so.3 /usr/bin/edb_streamd \
    > /data/edb_d.log 2>&1 &
sleep 1

# 7. Keep USB watcher stopped until rbp has initialized.
sh /data/usb-watch.sh stop 2>/dev/null || true

# 8. Launch rbp with the same display/touch/control shims as Prime GO.
nohup chroot "$CHROOT" env \
    DFB_ROTATE=left \
    JOG_VERBOSE=1 \
    TEMPO_VERBOSE=1 \
    KNOB_VERBOSE=1 \
    LD_PRELOAD=/usr/lib/fbshim.so:/usr/lib/audioshim.so:/usr/lib/knobshim.so \
    /lib/ld-linux.so.3 /root/pdj/rbp -a \
    </dev/null >/data/rbp-p.log 2>&1 &
RBP=$!

echo "launched rbp on JC16, waiting for initialization..."
i=0
while [ "$i" -lt 5 ]; do
    sleep 1
    kill -0 "$RBP" 2>/dev/null || fail "rbp exited; inspect /data/rbp-p.log"
    i=$((i + 1))
done

# 9. Start USB watcher after rbp is up.
# Prime 2 USB bus mapping has not been verified; opt in after measurement.
if [ -n "${USBWATCH_BUSES:-}" ]; then
    [ -x /data/timeout ] || fail "USB watcher requires /data/timeout"
    export USBWATCH_BUSES
    sh /data/usb-watch.sh start || fail "USB watcher failed"
fi

ENGINE_STOPPED=0
echo "PrimeBox JC16 started"
echo "rollback: sh /data/stop-rb-jc16.sh"
