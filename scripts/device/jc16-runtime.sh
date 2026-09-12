#!/bin/sh
# Shared process selection: only actual players/daemons rooted in our chroot.
primebox_pids() {
    for entry in "${1:-/proc}"/[0-9]*; do
        [ -d "$entry" ] || continue
        [ "$(readlink "$entry/root" 2>/dev/null)" = /data/rbx3-run ] || continue
        executable=$(readlink "$entry/exe" 2>/dev/null) || continue
        case "$executable" in
            /data/rbx3-run/root/pdj/rbp|/data/rbx3-run/usr/bin/edb_streamd|/data/rbx3-run/lib/ld-2.13.so)
                # Explicit loader invocations expose ld.so as exe. Match a full
                # argv token so debuggers and similarly named files survive.
                if tr '\000' '\n' <"$entry/cmdline" | grep -Ex '/root/pdj/rbp|/usr/bin/edb_streamd' >/dev/null; then
                    echo "${entry##*/}"
                fi
                ;;
        esac
    done
}
