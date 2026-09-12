#!/bin/sh
set -u
. /data/jc16-runtime.sh
status=0

# Stop only our watcher, validating its command instead of trusting a stale PID.
for entry in /proc/[0-9]*; do
    [ -r "$entry/cmdline" ] || continue
    args=$(tr '\000' '\n' <"$entry/cmdline")
    if printf '%s\n' "$args" | grep -Fx /data/usb-watch.sh >/dev/null &&
       printf '%s\n' "$args" | grep -Fx run >/dev/null; then
        kill "${entry##*/}" 2>/dev/null || true
    fi
done

for p in $(primebox_pids); do kill "$p" 2>/dev/null || true; done
sleep 2
# Revalidate membership before escalating; never kill generic strace/gdbserver.
for p in $(primebox_pids); do kill -9 "$p" 2>/dev/null || true; done
sleep 1
if [ -n "$(primebox_pids)" ]; then
    echo 'ERROR: PrimeBox processes still hold hardware; Engine not restarted' >&2
    exit 1
fi

# Release the USB bind first, then the chroot device/system mounts.
if mountpoint -q /data/rbx3-run/media/usb1/sda1; then
    umount /data/rbx3-run/media/usb1/sda1 || status=1
    if [ "$status" = 0 ] && mountpoint -q /media/usb1/sda1; then
        umount /media/usb1/sda1 || status=1
    fi
fi
for target in dev proc sys tmp; do
    if mountpoint -q "/data/rbx3-run/$target"; then
        umount "/data/rbx3-run/$target" || status=1
    fi
done
chmod 600 /dev/mem 2>/dev/null || status=1

systemctl start edisksd.service || status=1
systemctl start engine.service || status=1
systemctl is-active --quiet edisksd.service || status=1
systemctl is-active --quiet engine.service || status=1
if [ "$status" = 0 ]; then
    echo 'PrimeBox stopped; Engine OS services active'
else
    echo 'ERROR: rollback incomplete; inspect mounts and Engine OS service status' >&2
fi
exit "$status"
