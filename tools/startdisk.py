#!/usr/bin/env python3
"""startdisk.py - make a 400K startup floppy: System Folder + your programs.

  tools/startdisk.py OUT.dsk --system mac/System.dsk [--name Programs] APP.bin...

Starts from an empty MFS disk named --name, copies the boot blocks of the
system disk, puts the system files (System, Finder and every other file of
the system disk that is not an application) into a "System Folder" and the
programs (MacBinary files from mac68k-asm) next to it.

MFS has no real folders: the Finder keeps them in its invisible DeskTop file
(a resource 'FOBJ' per folder, its ID = the folder number) and every file
names its folder in its Finder info (fdFldr). This tool writes both. The
files go on the disk with mac68k-disk; only the Finder info in the directory
is patched here.
"""

import argparse
import calendar
import os
import struct
import subprocess
import sys
import tempfile
import time

FOLDER_ID = 17423                   # the number the Finder itself chose
MAC_EPOCH = 2082844800              # 1904-01-01 in Unix time

# An FOBJ as Finder 5.3 writes it for a folder in the disk's top window:
# 94 bytes, then the name as a Pascal string. Offsets used below: 2 the
# icon's place (v, h), 26/30 creation/modification date, 46 the folder
# window (top, left, bottom, right), 62 the number of items.
FOBJ_FOLDER = bytes.fromhex(
    "0008 0000 0000 0000 0083 0100 0000 0000"
    "fff2 0043 0000 0000 ffee e6e1 d929 e6e1"
    "d934 ffff 003e 0000 0000 0000 0052 0018"
    "010e 01ac fff8 fff0 0000 0000 0002 0000"
    "ffee" + "00" * 28)
assert len(FOBJ_FOLDER) == 94
# ... and for the disk itself (ID 0): icon on the desktop at the top right,
# window below the menu bar
FOBJ_DISK = bytes.fromhex(
    "0004 001c 01c8 0000 0081 0180 fffe 0000"
    "fffe 002e d200 0000 ffe6 e6e1 d8b1 e6e1"
    "d922 ffff 003e 0040 0000 0000 003e 000e"
    "00fa 01a2 fff8 fff0 0007 991a 0002 0000"
    "ffe6" + "00" * 28)
assert len(FOBJ_DISK) == 94


def run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"startdisk: {' '.join(cmd)}\n{r.stdout}{r.stderr}")
    return r.stdout


def mfs_files(image):
    """[(name, type, creator, offset of the directory entry)] of an MFS disk."""
    d = open(image, "rb").read()
    sig, = struct.unpack(">H", d[1024:1026])
    if sig != 0xD2D7:
        sys.exit(f"startdisk: {image} is not an MFS disk (a Mac 512K boots only MFS)")
    dirst, bllen = struct.unpack(">HH", d[1024 + 14:1024 + 18])
    out = []
    for b in range(dirst, dirst + bllen):
        o = 0
        while o < 512 - 51:
            e = b * 512 + o
            if not d[e] & 0x80:
                break
            ftype, creator = d[e + 2:e + 6], d[e + 6:e + 10]
            nlen = d[e + 50]
            out.append((d[e + 51:e + 51 + nlen].decode("mac_roman"), ftype, creator, e))
            o += 51 + nlen
            o += o & 1
    return out


def resource_fork(resources):
    """A resource fork from [(type, id, name, data)]."""
    data, types = b"", {}
    for rtype, rid, name, body in resources:
        types.setdefault(rtype, []).append((rid, name, len(data)))
        data += struct.pack(">I", len(body)) + body
    tlist = struct.pack(">h", len(types) - 1)
    refs, names = b"", b""
    ref_base = 2 + 8 * len(types)
    for rtype, items in types.items():
        tlist += rtype + struct.pack(">hH", len(items) - 1, ref_base + len(refs))
        for rid, name, off in items:
            noff = -1
            if name:
                noff = len(names)
                raw = name.encode("mac_roman")
                names += bytes([len(raw)]) + raw
            # ID, name offset, attributes, data offset (3 bytes), handle
            refs += struct.pack(">hhB", rid, noff, 0) + off.to_bytes(3, "big") + b"\0" * 4
    tl = tlist + refs
    rmap_len = 28 + len(tl) + len(names)
    header = struct.pack(">IIII", 256, 256 + len(data), len(data), rmap_len)
    rmap = header + b"\0" * 4 + b"\0" * 2 + b"\0" * 2 + struct.pack(">HH", 28, 28 + len(tl)) + tl + names
    return header + b"\0" * 240 + data + rmap


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("apps", nargs="*")
    ap.add_argument("--system", required=True)
    ap.add_argument("--name", default="Programs")
    args = ap.parse_args()

    system = [f for f in mfs_files(args.system)
              if f[0] != "DeskTop" and f[1] != b"APPL"]
    tmp = tempfile.mkdtemp(prefix="startdisk-")
    if os.path.exists(args.out):
        os.remove(args.out)
    run("mac68k-disk", "new", args.out, "--name", args.name)
    with open(args.system, "rb") as src, open(args.out, "r+b") as dst:
        dst.write(src.read(1024))                       # boot blocks
    for name, *_ in system:
        mb = os.path.join(tmp, f"{len(os.listdir(tmp))}.bin")
        run("mac68k-disk", "get", args.system, name, "-o", mb)
        run("mac68k-disk", "add", args.out, mb)
    for app in args.apps:
        run("mac68k-disk", "add", args.out, app, "-f")

    now = calendar.timegm(time.localtime()) + MAC_EPOCH     # the Mac keeps local time

    def fobj(template, name, items):
        f = bytearray(template)
        struct.pack_into(">II", f, 26, now, now)
        struct.pack_into(">H", f, 62, items)
        raw = name.encode("mac_roman")
        return bytes(f) + bytes([len(raw)]) + raw
    empty = os.path.join(tmp, "empty")
    open(empty, "wb").close()
    fork = os.path.join(tmp, "DeskTop.rsrc")
    open(fork, "wb").write(resource_fork([
        (b"STR ", 0, "", b"\x0aFinder 1.0"),                # the DeskTop's version
        (b"FOBJ", FOLDER_ID, "System Folder", fobj(FOBJ_FOLDER, "System Folder", len(system))),
        (b"FOBJ", 0, args.name, fobj(FOBJ_DISK, args.name, 1 + len(args.apps))),
    ]))
    run("mac68k-disk", "add", args.out, empty, "--name", "DeskTop",
        "--type", "FNDR", "--creator", "ERIK", "--rsrc", fork)

    # Finder info in the directory: fdFlags at +10 of the entry, fdFldr at +16
    in_folder = {name for name, *_ in system}
    with open(args.out, "r+b") as f:
        for name, _, _, e in mfs_files(args.out):
            if name in in_folder:
                f.seek(e + 16)
                f.write(struct.pack(">h", FOLDER_ID))
            elif name == "DeskTop":
                f.seek(e + 10)
                f.write(struct.pack(">H", 0x4000))      # invisible
    print(run("mac68k-disk", "ls", "-l", args.out), end="")


if __name__ == "__main__":
    main()
