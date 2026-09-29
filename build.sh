#!/bin/bash
# build.sh - build a program and put it on floppy disk images.
#
#   ./build.sh [NAME]        (default: Hello; builds src/NAME.Job)
#   ./build.sh all           every program in src/, onto a fresh Programs.dsk
#
# Results in out/:
#   NAME.bin       the application (MacBinary)
#   Programs.dsk   400K floppy "Programs" with every program built so far.
#                  With mac/System.dsk it is a startup disk: the system files
#                  in a System Folder plus the programs, booting into the
#                  Finder - start Mini vMac with it, or write it to a floppy
#                  for a real Mac.
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

# every application built so far (out/ also holds the linker's .code.bin files)
apps=()
for bin in out/*.bin; do
    [ "$(dd if="$bin" bs=1 skip=65 count=4 status=none)" = APPL ] && apps+=("$bin")
done

rm -f out/Programs.dsk out/Test.dsk
if [ -f mac/System.dsk ]; then
    mac68k-disk new out/Programs.dsk --system mac/System.dsk
else
    mac68k-disk new out/Programs.dsk
fi
mac68k-disk add out/Programs.dsk "${apps[@]}"
if [ -f mac/System.dsk ]; then
    cp out/Programs.dsk out/Test.dsk
    mac68k-disk startup out/Test.dsk "$NAME"
fi

mac68k-disk ls -l -R out/Programs.dsk
