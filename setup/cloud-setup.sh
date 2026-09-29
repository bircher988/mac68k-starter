#!/bin/bash
# cloud-setup.sh - setup script for a Claude Code on the web environment.
#
# Paste it into the "Setup script" field of your environment at
# claude.ai/code. It runs as root on the cloud machine (Ubuntu 24.04) before
# Claude starts, and the result is cached for later sessions.
#
# Installs:
#   mac68k-asm   68000 assembler, linker and resource compiler
#   mac68k-disk  Mac floppy disk images (MFS 400K / HFS)
#   minivmac     Mini vMac emulating a Macintosh 512K (64K ROM), for headless
#                tests with tools/macemu.py; built from source
#   xvfb, xdotool  a virtual screen for the emulator
#
# Also works on a Debian/Ubuntu machine of your own (amd64 or arm64).
set -euo pipefail

ARCH=$(dpkg --print-architecture)
VERSION=1.1
cd /tmp

for tool in mac68k-asm mac68k-disk; do
    curl -fsSLO "https://github.com/bircher988/$tool/releases/download/v$VERSION/${tool}_${VERSION}_$ARCH.deb"
done
# the cloud image lists some package sources (PPAs) that the "Trusted" network
# level blocks: their errors don't matter, the Ubuntu archive is reachable
apt-get update -q || true
apt-get install -y -q ./mac68k-asm_${VERSION}_$ARCH.deb ./mac68k-disk_${VERSION}_$ARCH.deb \
    build-essential git libx11-dev libxtst6 xvfb xdotool

# Mini vMac: Mac 128K board with 512 KB RAM = Macintosh 512K, real speed (1x),
# no sound (the cloud machine has no audio device)
rm -rf minivmac
git clone -q https://github.com/minivmac/minivmac.git
cd minivmac
git checkout -q 6860a9a
gcc -o setup_t setup/tool.c
if [ "$ARCH" = arm64 ]; then TARGET="-t larm -cpu a64"; else TARGET="-t lx64"; fi
./setup_t $TARGET -m 128K -mem 512K -sound 0 -speed z > setup.sh
bash setup.sh
make -j"$(nproc)"
install -m 755 minivmac /usr/local/bin/minivmac

mac68k-asm version
mac68k-disk version
