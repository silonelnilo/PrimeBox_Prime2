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

# RX3 glibc 2.13 predates the modern 64-bit time/off_t transition on 32-bit
# ARM.  Ubuntu's current armel cross headers default to the new ABI, so pin
# both knobs to 32 to keep the generated interposition symbols compatible.
CFLAGS  := -O2 -march=armv5t -mfloat-abi=soft -fno-stack-protector -fPIC \
           -U_FILE_OFFSET_BITS -D_FILE_OFFSET_BITS=32 \
           -U_TIME_BITS -D_TIME_BITS=32 \
           -Wall -Wextra -Wno-unused-parameter
LDFLAGS := -L$(RX3LIB) -L$(RX3ULIB) -Wl,-rpath-link,$(RX3LIB):$(RX3ULIB)

SHARED  := knobshim2.so audioshim.so fbshim-tsc.so gpioshim.so tscshim.so crashcatch.so
STATIC  := seqinject2 udplog

.PHONY: all clean check
all: $(SHARED) $(STATIC)

knobshim2.so: knobshim2.c legacy-scan.c
	$(CC) $(CFLAGS) -shared -o $@ $^ -lpthread -lc $(LDFLAGS)

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

check: $(SHARED)
	@echo "== GLIBC symbol versions =="
	@for f in $(SHARED); do \
	  echo "-- $$f"; \
	  $(CROSS)objdump -T $$f 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sort -u; \
	  $(CROSS)readelf -A $$f | grep -i 'Tag_ABI_VFP_args' && echo "  !! HARD-FLOAT" || true; \
	done

clean:
	rm -f $(SHARED) $(STATIC) *.o
