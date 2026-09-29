#!/bin/bash
# build.sh - build a program and put it on floppy disk images.
#
#   ./build.sh [NAME]        (default: Hello; builds src/NAME.Job)
#
# Results in out/:
#   NAME.bin    the application (MacBinary)
#   Apps.dsk    400K floppy with every program built so far - for your own
#               emulator or a real Mac
#   Test.dsk    only if mac/System.dsk exists: a copy of the system disk plus
#               the program, set up to boot straight into it
#               (for tools/macemu.py)
set -euo pipefail
cd "$(dirname "$0")"

NAME="${1:-Hello}"
mkdir -p out

mac68k-asm build "src/$NAME.Job" -o out
[ -f "out/$NAME.bin" ] || { echo "build.sh: out/$NAME.bin was not made" >&2; exit 1; }

[ -f out/Apps.dsk ] || mac68k-disk new out/Apps.dsk
mac68k-disk add out/Apps.dsk "out/$NAME.bin" -f

if [ -f mac/System.dsk ]; then
    cp mac/System.dsk out/Test.dsk
    mac68k-disk add out/Test.dsk "out/$NAME.bin" -f
    mac68k-disk startup out/Test.dsk "$NAME"
fi

mac68k-disk ls -l out/Apps.dsk
