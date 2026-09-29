# Mac programs in 68000 assembler

Programs for the original Macintosh 512K: 64K ROM, 512 KB RAM, 8 MHz 68000, 512x342
black-and-white screen, System 3.2, 400K MFS floppies. Written in 68000 assembler with
mac68k-asm, put on disk images with mac68k-disk, tested headless in Mini vMac.

## Tools
- A program is four text files in `src/`: `NAME.Asm` (code), `NAME.Link` (modules),
  `NAME.R` (resources: windows, menus, ...) and `NAME.Job` (ties them together).
  A new program starts as a copy of the Hello files with every "Hello" renamed.
- Build: `./build.sh NAME` -> `out/NAME.bin`, `out/Apps.dsk` (400K floppy with all
  programs) and `out/Test.dsk` (system disk that boots straight into NAME). A failed
  build exits with status 1: check it, never filter warnings away.
- Assembler manual: `/usr/local/share/doc/mac68k-asm/README.md` (dialect, directives,
  `.R` syntax). Include files: `/usr/share/mac68k-asm/inc/` (Traps.D, ToolEqu.D,
  QuickEqu.D, SysEqu.D, ...) - grep them for trap names and equates.
- Disk images: `mac68k-disk help`.
- Test: `tools/macemu.py "boot; shot start; click 256 171; wait 1; shot after"` boots
  `out/Test.dsk` in Mini vMac at real speed, plays the steps and saves screenshots in
  `out/shots/`. Steps: see `tools/macemu.py --help`. **Look at the screenshots** (read
  the PNG files) after every change you can see; don't assume that it works.
- The emulator needs `mac/Mac128K.ROM` and `mac/System.dsk` (see mac/README.md). If
  they are missing, say so once and only build.
- Tools missing (`mac68k-asm: command not found`)? Run `setup/cloud-setup.sh` as root
  (with `sudo` if you are not root).

## The machine
- 64K ROM only: no traps of the Mac Plus ROM (the assembler warns about them), no
  hierarchical folders, no color. Screen 512x342, 1 bit.
- The keyboard has no arrow keys and no Control key; Command-key shortcuts work.
- The QuickDraw globals are set up with `PEA -4(A5)` / `_InitGraf`; the standard arrow
  cursor is then at `arrow-4(A5)` (`QDArrow EQU arrow-4`, then `PEA QDArrow(A5)` /
  `_SetCursor`). Call `_InitCursor` only once, at start-up.

## Assembler rules that bite
- `DS` variables live in the A5 globals area, not in the code. Read them as `Var`,
  write them as `Var(A5)`. **Never use A5 as a working register.** In a VBL task or
  interrupt code A5 is undefined: load it from `CurrentA5` ($904) first.
- DS variables are **not zeroed** at launch: set every flag, counter and pointer in
  the init code before it is read.
- Traps preserve only D3-D7 and A2-A6. D0-D2 and A0-A1 are gone after every trap:
  keep loop counters, coordinates and pointers in D3-D7/A2-A4.
- Pascal convention for Toolbox calls: push room for the result, push the arguments
  left to right, call the trap, pop the result. A BOOLEAN sits in the **high** byte of
  its word (`MOVE.W #$0100,-(SP)` = TRUE, `TST.B (SP)+` reads a result), a CHAR in the
  **low** byte.
- Keep code even: a label right after an odd-length `DC.B` string stays on an odd
  address, and a jump there crashes with bomb ID=03. Put `EVEN` after strings, or keep
  all data at the end of the module.
- Bomb ID=03 somewhere unexpected: first suspect a trap that destroyed D0-D2/A0-A1, or
  a write through a wrong pointer - the bomb rarely points at the cause.

## Working style
- Small steps: build, test in the emulator, look at the screenshot, then go on.
- Commit after every working step with a short message.
- Before you finish: `./build.sh NAME` once more, copy `out/Apps.dsk` to `disk/Apps.dsk`
  and the final screenshot to `shots/NAME.png` (both folders are committed, out/ is
  not), commit, and say in one line what the program does and how to use it.
