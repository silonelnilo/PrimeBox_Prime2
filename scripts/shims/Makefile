# PrimeBox shim build
#
# All shims must be soft-float EABI5 and reference only GLIBC_2.4/2.7, because
# they are LD_PRELOADed into the XDJ-RX3 soft-float glibc-2.13 chroot.
#
# Usage:
#   make RX3=/path/to/extracted/XDJRX3-rootfs
#   make clean
#
# The RX3 rootfs is used as the sysroot for libc/libdl/librt/pthread so symbol
# versioning matches the target (modern host glibc would pull in GLIBC_2.17+).

CROSS   ?= arm-linux-gnueabi-
CC      := $(CROSS)gcc
STRIP   ?= $(CROSS)strip

RX3     ?= ../../extracted/XDJRX3-rootfs
RX3LIB  := $(RX3)/lib
RX3ULIB := $(RX3)/usr/lib

# RX3 userspace is a 32-bit glibc-2.13 ABI.  Explicitly pin 32-bit file
# offsets so modern cross-toolchain headers do not redirect open() to open64(),
# which breaks fbshim-tsc because it intentionally interposes both symbols.
CFLAGS  := -O2 -march=armv5t -mfloat-abi=soft -fno-stack-protector -fPIC \
           -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 \
           -Wall -Wextra -Wno-unused-parameter
LDFLAGS := -L$(RX3LIB) -L$(RX3ULIB) -Wl,-rpath-link,$(RX3LIB):$(RX3ULIB)

# Shared LD_PRELOAD libraries (soft-float, libc-only NEEDED)
SHARED  := knobshim2.so audioshim.so fbshim-tsc.so gpioshim.so tscshim.so crashcatch.so

# Static ARM helpers (have no soft-float runtime dependency)
STATIC  := seqinject2 udplog

.PHONY: all clean check
all: $(SHARED) $(STATIC)

# knobshim2 needs the ALSA sequencer headers; host headers are fine as the
# structs are ABI-stable.
knobshim2.so: knobshim2.c
	$(CC) $(CFLAGS) -shared -o $@ $< -lpthread -lc $(LDFLAGS)

# audioshim must bind dlopen/dlsym to libdl GLIBC_2.4 (the .symver directives
# are in the source); link the RX3 libdl explicitly.
audioshim.so: audioshim.c
	$(CC) $(CFLAGS) -shared -o $@ $< $(RX3LIB)/libdl.so.2 -lc $(LDFLAGS)

fbshim-tsc.so: fbshim-tsc.c
	$(CC) $(CFLAGS) -shared -o $@ $< -lpthread -lc $(LDFLAGS)

gpioshim.so: gpioshim.c
	$(CC) $(CFLAGS) -shared -o $@ $< -lc $(LDFLAGS)

tscshim.so: tscshim.c
	$(CC) $(CFLAGS) -shared -o $@ $< -lpthread -lc $(LDFLAGS)

crashcatch.so: crashcatch.c
	$(CC) $(CFLAGS) -shared -o $@ $< -lc $(LDFLAGS)

seqinject2: seqinject2.c
	$(CC) -O2 -march=armv5t -mfloat-abi=soft -static -o $@ $<

udplog: udplog.c
	$(CC) -O2 -march=armv5t -mfloat-abi=soft -static -o $@ $<

# Fail the build if any GLIBC version above 2.7 or a hard-float tag sneaks in.
check: $(SHARED)
	@echo "== GLIBC symbol versions =="
	@for f in $(SHARED); do \
	  echo "-- $$f"; \
	  $(CROSS)objdump -T $$f 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sort -u; \
	  $(CROSS)readelf -A $$f | grep -i 'Tag_ABI_VFP_args' && echo "  !! HARD-FLOAT" || true; \
	done

clean:
	rm -f $(SHARED) $(STATIC) *.o
