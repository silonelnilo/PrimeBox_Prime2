#!/bin/sh
set -u

# Stop PrimeBox processes and hand hardware back to Engine OS.

sh /data/usb-watch.sh stop 2>/dev/null || true

for p in $(ps w | awk '$0 ~ /[r]oot\/pdj\/[r]bp|[e]db_streamd|[g]dbserver|[s]trace/ {print $1}'); do
    kill -9 "$p" 2>/dev/null || true
done

# Restore /dev/mem permissions changed by fix-dev.sh.
chmod 600 /dev/mem 2>/dev/null || true

# Restart normal Denon services.
systemctl start edisksd.service 2>/dev/null || true
systemctl start engine.service 2>/dev/null || true

echo "PrimeBox stopped; Engine OS restart requested"
