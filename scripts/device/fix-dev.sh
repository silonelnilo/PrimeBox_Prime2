#!/bin/sh
set -eu
# Never recursively delete a directory that may still bind the host /dev.
if mountpoint -q /data/rbx3-run/dev; then
  umount /data/rbx3-run/dev
fi
mkdir -p /data/rbx3-run/dev
mount --bind /dev /data/rbx3-run/dev
mountpoint -q /data/rbx3-run/proc || mount --bind /proc /data/rbx3-run/proc
mountpoint -q /data/rbx3-run/sys  || mount --bind /sys  /data/rbx3-run/sys
mountpoint -q /data/rbx3-run/tmp  || mount --bind /tmp  /data/rbx3-run/tmp
echo "fb0: $(ls -la /data/rbx3-run/dev/fb0 | awk '{print $1}')"
echo "dev mounted: $(mountpoint -q /data/rbx3-run/dev && echo yes)"
# FIFOs for devices that threads poll/read, preventing 100% CPU busy-spin:
for d in subucom_spi1.0 subucom_spi2.0 subucom_spi_rdy3.0 subucom_spi_rdy4.0 hidg0; do
  rm -f /data/rbx3-run/dev/$d
  mkfifo /data/rbx3-run/dev/$d 2>/dev/null || mknod /data/rbx3-run/dev/$d p
  chmod 666 /data/rbx3-run/dev/$d 2>/dev/null
done

# Regular file stubs for ioctl-only devices and polled GPIOs:
for d in printkdrv0 tsc2007_2-0048 gpiodrv; do
  rm -f /data/rbx3-run/dev/$d 2>/dev/null
  touch /data/rbx3-run/dev/$d
  chmod 666 /data/rbx3-run/dev/$d 2>/dev/null
done
# Ensure paudiog0 is NOT present so JUCE skips gadget audio ioctl
rm -f /data/rbx3-run/dev/paudiog0
# Block /dev/mem to prevent rbp from reading unmapped i.MX6 registers
chmod 000 /dev/mem /data/rbx3-run/dev/mem 2>/dev/null

# Ensure udev FIFOs exist in /tmp for USB stick detection:
for f in udev_usb1 udev_usb2 udev_usbctn1 udev_usbctn2; do
  [ -p /tmp/$f ] || { rm -f /tmp/$f; mkfifo /tmp/$f; chmod 666 /tmp/$f; }
done

# Standard mtab symlink for POSIX getmntent / vfs_getfsys
ln -sf /proc/mounts /data/rbx3-run/etc/mtab 2>/dev/null

echo "stubs done"
