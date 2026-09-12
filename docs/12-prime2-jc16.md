# 12 — Denon Prime 2 / JC16 port

This branch is an experimental port of PrimeBox from Prime GO (JP11) to Prime 2 (JC16).

## Measured hardware

The following values were measured on a Prime 2 running Engine OS 5.0.4 with root SSH access.

| Area | Prime 2 / JC16 |
|---|---|
| SoC | Rockchip RK3288, ARMv7 |
| Display | DSI `800x1280`, RGB32, stride 3200 |
| Framebuffer | `/dev/fb0`, virtual size `800x3840` (triple buffer) |
| Touch | ILI2116, `/dev/input/event0` |
| Control surface | `PRIME 2 Control Surface`, ALSA sequencer `16:0` |
| Audio | ALSA card `JC16`, device 0 |
| Playback | `S32_LE`, 4 channels, 44100 Hz |
| Capture | `S32_LE`, 2 channels, 44100 Hz |
| Engine playback period/buffer observed | 256 / 512 frames |

The display geometry and evdev touch path are close enough to Prime GO that the first boot test intentionally keeps the existing DirectFB/fb/touch shims unchanged.

## Control mapping verified live

ALSA sequencer channels below are zero-based, as printed by `aseqdump`.

| Control | Prime 2 MIDI |
|---|---|
| Left PLAY | ch2 note10 |
| Left CUE | ch2 note9 |
| Left SYNC | ch2 note8 |
| Right PLAY | ch3 note10 |
| Right CUE | ch3 note9 |
| Right SYNC | ch3 note8 |
| Pad 1 | note15 on deck channel |
| LOAD 1 / LOAD 2 | ch15 note1 / note2 |
| Browse push | ch15 note6 |
| Browse rotate | ch15 CC5, relative (`1`=CW, `127`=CCW) |
| Pitch | deck ch, CC31 MSB + CC75 LSB, 14-bit |
| Jog touch | deck ch, note33 |
| Jog position | deck ch, CC55 MSB + CC77 LSB, 14-bit |
| Left / right channel fader | ch0 / ch1, CC14 |
| Crossfader | ch15 CC14 |
| Left EQ high | ch0 CC4 |
| Left filter/color knob | ch0 CC11 |

These values match the existing Prime GO `knobshim2.c` layout for the controls tested so far. Therefore the first JC16 boot test deliberately uses `knobshim2.so` unchanged. Differences will be added only when observed.

## Audio mismatch

Prime GO PrimeBox currently opens `hw:1,0` and forces `S24_LE / 44100 / 4ch`. JC16 exposes a named ALSA device `hw:JC16,0` and was observed running `S32_LE / 44100 / 4ch`.

For the first test, `scripts/shims/build-jc16-audioshim.sh` generates a temporary JC16 variant from the upstream `audioshim.c` without changing the Prime GO source. It changes only the real hardware device and the hardware PCM format.

The existing 4-channel routing is retained:

- channels 0/1: master L/R
- channels 2/3: headphones L/R

No assumption is yet made that the Prime 2 accepts the Prime GO 64-frame period. ALSA negotiation is left to the existing shim for the first test; if it fails or produces XRUNs, the measured 256-frame JC16 period will be tested next.

## First milestone scope

The first milestone is intentionally small: boot `rbp`, get the main display/touch, browse/load, PLAY/CUE, and master/headphone audio working. Jog displays and secondary LEDs are out of scope until the basic path is stable.

All runtime deployment should remain under `/data`; do not modify the read-only root filesystem for this port.

## JC16 open payload and first test

The `Build Prime 2 JC16 open payload` workflow now produces a single
`prime2-jc16-open-payload.tar.gz` with the JC16 audio shim, control/touch shims,
DirectFB module, runtime helpers, scripts, checksums and source commit ID.
The archive preserves executable permissions. Extract it in a staging directory
and run `sha256sum -c SHA256SUMS.txt` **from that directory** before copying files.

This is an open-source payload, not yet a complete RX3 deployment: it excludes
the proprietary RX3 chroot, fonts, player and decryption key. Prepare those from
your own official RX3 1.20 firmware as described in `docs/01-firmware-extraction.md`.
Do not substitute the link sysroot used by CI for a fully assembled runtime.
The latter must contain the complete runtime symlinks, fonts, ALSA configuration,
DeviceSQL daemon and patched `rbp-audio`.

Stage the runtime at `/data/rbx3-run` and the payload files directly under
`/data`. Preserve any existing files before replacing them. Do not install a
boot menu entry or change SSH, firmware, system services, rootfs or bootloader.
The first launch is manual: `sh /data/start-rb-jc16.sh`. Stop and return to
Engine OS with `sh /data/stop-rb-jc16.sh`.

The launcher checks JC16 hardware and required files before stopping Engine.
It rolls back on preparation errors and signals, and requires rbp to survive
five seconds before reporting startup. This is a process-liveness check, not
proof that display, controls or audio work. The stop script selects processes
by their chroot and executable/arguments, stops them, releases runtime mounts,
and checks that Engine and edisksd are active. A rollback error is reported
with a nonzero status.

USB hotplug is off by default: the inherited watcher assumes Prime GO buses
3/4, which have not been measured on Prime 2. Enable it only after confirming
the correct external USB host buses, by passing `USBWATCH_BUSES` to the launcher.
That mode also requires an executable `/data/timeout`; it is not in this payload.

## Build #14 diagnosis and regression checks

Run `34688601573` at commit `54f51b580f3e966d3ac749c12c2f46339b34ad4f`
built the DirectFB module and printed `DirectFB module GLIBC: GLIBC_2.4`,
then exited 1 during post-build validation. Its final objdump check searched
`__fxstat.*GLIBC_2.4`; GNU objdump prints the version **before** the symbol,
so that expression cannot validate the intended import. The replacement
validator parses symbols separately and reports missing exports, wrong GLIBC,
wrong ELF/float ABI, wrong DirectFB dependencies and leftover build RPATHs.

Run the host-side regression tests with:

```sh
python3 -m unittest discover -s tests -v
```

They exercise the symbol-column regression, incompatible/missing symbols,
process selection, rollback service failures, rollback on unexpected startup
failure, and aborting device setup after failed unmount. Hardware testing is
still required; these tests do not connect to a Prime 2.
