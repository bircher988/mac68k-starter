#!/bin/bash
# build.sh - build a program and put it on floppy disk images.
#
#   ./build.sh [NAME]        (default: Hello; builds src/NAME.Job)
#   ./build.sh all           every program in src/, onto a fresh Programs.dsk
#
# Results in out/:
#   NAME.bin       the application (MacBinary)
#   Programs.dsk   400K floppy with every program built so far. With
#                  mac/System.dsk it is a startup disk: the system disk plus
#                  the programs, booting into the Finder - start Mini vMac
#                  with it, or write it to a floppy for a real Mac.
#   Test.dsk       only with mac/System.dsk: Programs.dsk set up to boot
#                  straight into NAME (for tools/macemu.py)
set -euo pipefail
cd "$(dirname "$0")"

NAME="${1:-Hello}"
mkdir -p out

if [ "$NAME" = all ]; then
    rm -f out/Programs.dsk out/Test.dsk
    for job in src/*.Job; do
        "$0" "$(basename "$job" .Job)"
    done
    exit 0
fi

mac68k-asm build "src/$NAME.Job" -o out
[ -f "out/$NAME.bin" ] || { echo "build.sh: out/$NAME.bin was not made" >&2; exit 1; }

if [ ! -f out/Programs.dsk ]; then
    if [ -f mac/System.dsk ]; then
        cp mac/System.dsk out/Programs.dsk
    else
        mac68k-disk new out/Programs.dsk --name Programs
    fi
fi
mac68k-disk add out/Programs.dsk "out/$NAME.bin" -f

if [ -f mac/System.dsk ]; then
    cp out/Programs.dsk out/Test.dsk
    mac68k-disk startup out/Test.dsk "$NAME"
fi

mac68k-disk ls -l out/Programs.dsk
