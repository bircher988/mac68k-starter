# mac68k-starter

A template for writing programs for the original Macintosh (128K/512K, 1984) in 68000
assembler - with [Claude Code on the web](https://claude.ai/code), in your browser, or on
your own Linux machine.

- [mac68k-asm](https://github.com/bircher988/mac68k-asm): assembler, linker and resource
  compiler in one program
- [mac68k-disk](https://github.com/bircher988/mac68k-disk): Mac floppy disk images
- [Mini vMac](https://github.com/minivmac/minivmac): emulator, runs headless for tests
- `CLAUDE.md`: what Claude needs to know about the tools, the machine and the traps of
  68000 programming on the Mac

## Claude Code on the web

1. **Use this template** -> *Create a new repository* -> **Private** (your ROM will go
   in there).
2. Upload `Mac128K.ROM` (from your own Mac) and a System 3.x startup disk as
   `System.dsk` into the `mac/` folder - see [mac/README.md](mac/README.md). Without them
   Claude can build but not test.
3. Give the [Claude GitHub App](https://github.com/apps/claude) access to the new
   repository (*Configure* -> *Only select repositories*). A private repository only
   shows up in claude.ai/code after that.
4. On [claude.ai/code](https://claude.ai/code): open the environment menu (the cloud
   above the message box) -> *Cloud* -> *Add cloud environment*: name it `mac68k`,
   network access *Trusted*, and paste the contents of
   [`setup/cloud-setup.sh`](setup/cloud-setup.sh) into **Setup script**.
5. Select your repository and the `mac68k` environment, and ask for a program, e.g.
   *"Write a program that draws a bouncing ball. Quit on a click."*

Claude builds it, boots it in the emulator, looks at the screenshots, and hands you a
startup floppy - your system disk plus the program - as a download on a (private) Claude
artifact. Unzip it and open `Programs.dsk` with Mini vMac, or write it to a real floppy.

## On your own machine (Debian/Ubuntu)

    sudo bash setup/cloud-setup.sh
    ./build.sh                      # builds src/Hello.* -> out/Programs.dsk, out/Test.dsk
    tools/macemu.py "boot; shot start"

## Files

| | |
|---|---|
| `src/` | the programs: `NAME.Asm`, `NAME.Link`, `NAME.R`, `NAME.Job` |
| `build.sh` | build one program and put it on disk images |
| `tools/macemu.py` | run the Mac headless, click and type, take screenshots |
| `setup/cloud-setup.sh` | install everything (cloud environment or your machine) |
| `mac/` | your ROM and system disk (private repositories only) |

## Licence

MIT - see [LICENSE](LICENSE). Mini vMac is GPL-2.0 and is built from its own repository.
