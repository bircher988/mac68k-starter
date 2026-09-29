# Mac ROM and system disk

The emulator tests need two files from Apple that this template cannot include:

| File | What |
|---|---|
| `Mac128K.ROM` | the 64 KB ROM of a Macintosh 128K or 512K (read it from your own machine) |
| `System.dsk`  | a 400K startup floppy image with System 3.x and the Finder |

Both are copyrighted by Apple. **Only put them into a private repository**, and only
use a ROM of a Mac you own.

On github.com: open this folder in your (private) repository, then
**Add file -> Upload files**. (The `.gitignore` keeps them out of commits made with
git on your own machine, so they don't end up in a public repository by accident;
an upload on github.com is committed anyway.)

The floppy you get from Claude, `Programs.dsk`, is a copy of your system disk with
your programs added - keep the artifact it comes on private, too.

Without these files everything else still works: `./build.sh` makes the program and a
floppy image `out/Programs.dsk` with just the programs - open it in your own emulator
next to a system disk, or on a real Mac.
