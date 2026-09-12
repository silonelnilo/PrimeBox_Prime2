#!/bin/sh
set -eu

# PrimeBox launcher for Denon Prime 2 / JC16.
# This intentionally mirrors start-rb.sh but selects the JC16 audioshim.
# Runtime changes remain under /data; Engine OS is restored by stop-rb-jc16.sh.

AUDIO_SHIM=/data/audioshim-jc16.so

if [ ! -f "$AUDIO_SHIM" ]; then
    echo "missing $AUDIO_SHIM" >&2
    echo "copy the JC16 audioshim to /data before launching" >&2
    exit 1
fi

# 1. Release hardware currently owned by Engine OS.
systemctl stop engine.service edisksd.service 2>/dev/null || true
sleep 1

# 2. Kill stale PrimeBox processes only.
for p in $(ps w | awk '$0 ~ /[s]trace|[r]oot\/pdj\/[r]bp|[e]db_streamd|[g]dbserver|[u]sb-watch/ {print $1}'); do
    kill -9 "$p" 2>/dev/null || true
done
sleep 1

# 3. Setup device binds/stubs used by the RX3 userspace.
sh /data/fix-dev.sh

# 4. Deploy rbp and shims into the chroot.
cp /data/rbp-audio /data/rbx3-run/root/pdj/rbp
chmod 755 /data/rbx3-run/root/pdj/rbp

cp /data/knobshim2.so /data/rbx3-run/root/pdj/knobshim.so
cp /data/knobshim2.so /data/rbx3-run/usr/lib/knobshim.so
chmod 755 /data/rbx3-run/usr/lib/knobshim.so /data/rbx3-run/root/pdj/knobshim.so

cp "$AUDIO_SHIM" /data/rbx3-run/root/pdj/audioshim.so
cp "$AUDIO_SHIM" /data/rbx3-run/usr/lib/audioshim.so
chmod 755 /data/rbx3-run/usr/lib/audioshim.so /data/rbx3-run/root/pdj/audioshim.so

cp /data/fbshim-tsc.so /data/rbx3-run/root/pdj/fbshim.so
cp /data/fbshim-tsc.so /data/rbx3-run/usr/lib/fbshim.so
chmod 755 /data/rbx3-run/usr/lib/fbshim.so /data/rbx3-run/root/pdj/fbshim.so

cp /data/libdirectfb_fbdev-rot16.so /data/rbx3-run/usr/lib/directfb-1.4-6/systems/libdirectfb_fbdev.so
chmod 755 /data/rbx3-run/usr/lib/directfb-1.4-6/systems/libdirectfb_fbdev.so

# 5. Clean stale IPC/logs.
rm -f /tmp/guard_LocalDBServer /tmp/req_LocalDBServer \
      /tmp/knobshim.log /tmp/audioshim.log /tmp/dfbdig*.log \
      /tmp/rot_surface.dump /data/rbp-p.log

# 6. Start DeviceSQL daemon inside the chroot.
export EDB_BIN=/usr/bin
nohup chroot /data/rbx3-run /lib/ld-linux.so.3 /usr/bin/edb_streamd \
    > /data/edb_d.log 2>&1 &
sleep 1

# 7. Keep USB watcher stopped until rbp has initialized.
sh /data/usb-watch.sh stop 2>/dev/null || true

# 8. Launch rbp with the same display/touch/control shims as Prime GO.
nohup chroot /data/rbx3-run env \
    DFB_ROTATE=left \
    JOG_VERBOSE=1 \
    TEMPO_VERBOSE=1 \
    KNOB_VERBOSE=1 \
    LD_PRELOAD=/usr/lib/fbshim.so:/usr/lib/audioshim.so:/usr/lib/knobshim.so \
    /lib/ld-linux.so.3 /root/pdj/rbp -a \
    </dev/null >/data/rbp-p.log 2>&1 &

echo "launched rbp on JC16, waiting for initialization..."
RBP=""
i=0
while [ "$i" -lt 30 ]; do
    RBP=$(ps w | awk '/\/root\/pdj\/rbp/ && !/sh -c/ && !/awk/ {print $1; exit}')
    if [ -n "$RBP" ]; then
        echo "RBP=$RBP running"
        break
    fi
    i=$((i + 1))
    sleep 1
done

if [ -z "$RBP" ]; then
    echo "rbp did not stay running; inspect /data/rbp-p.log and /tmp/audioshim.log" >&2
    exit 1
fi

# 9. Start USB watcher after rbp is up.
sh /data/usb-watch.sh start 2>/dev/null || true

echo "PrimeBox JC16 started"
echo "rollback: sh /data/stop-rb-jc16.sh"
