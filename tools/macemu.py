#!/usr/bin/env python3
"""macemu.py - run a Mac program headless in Mini vMac and take screenshots.

Starts a private virtual screen (Xvfb), boots Mini vMac (Macintosh 512K,
64K ROM) from copies of the disk images, plays a list of steps - waits,
mouse clicks, keys - and saves screenshots as PNG files. Nothing but Python 3,
Xvfb, xdotool and libX11/libXtst is needed.

Usage:
  tools/macemu.py [STEPS] [--disk IMG ...] [--out DIR] [--rom FILE] [--emu FILE]

  STEPS   steps separated by ';' or newlines, or @FILE to read them from a
          file. Default: "boot; shot screen"
  --disk  disk images to insert, in order (default: out/Test.dsk, which
          ./build.sh makes: the system disk booting straight into the
          program). The images are copied first; the originals stay as they
          are.
  --out   where the screenshots go (default: out/shots)
  --rom   the Mac 128K/512K ROM (default: mac/Mac128K.ROM)
  --emu   the emulator (default: minivmac on the PATH)

Steps (coordinates are Mac screen pixels: x 0..511, y 0..341):
  boot [timeout=90]      wait until the menu bar is on the screen (the Finder
                         or a program that called InitWindows) and the
                         screen is still for a second
  wait S                 sleep S seconds (the Mac runs at its real speed)
  wait_stable [still=1.5] [timeout=60]
                         wait until the screen has not changed for `still` s
  wait_change [timeout=30]
                         wait until the screen differs from how it looked
                         when the step started
  shot NAME              save the screen as DIR/NAME.png (512x342)
  move X Y               move the mouse
  click [X Y]            click (at X,Y)
  dblclick [X Y]         double-click
  drag X1 Y1 X2 Y2       press at X1,Y1, move, release at X2,Y2
  key SPEC ...           press keys: a  Return  space  cmd+q  shift+a ...
                         (X keysym names; cmd = the Command key)
  hold K[,K...] S        hold keys down for S seconds (for games that poll
                         the keyboard once a frame; a `key` tap can be missed)
  type TEXT              type text
  speed 1x|2x|4x|8x|16x|all
                         emulation speed (starts at 1x = real Mac speed)

Example:
  tools/macemu.py "boot; shot start; click 256 171; wait 1; shot clicked"
"""

import argparse
import ctypes
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAC_W, MAC_H = 512, 342
SPEED_KEYS = {"1x": "z", "2x": "1", "4x": "2", "8x": "3", "16x": "4",
              "32x": "5", "all": "a"}
MODS = {"cmd": "Alt_L", "command": "Alt_L", "option": "Super_L",
        "opt": "Super_L", "shift": "Shift_L"}
CHARS = {" ": ("space", 0), ".": ("period", 0), ",": ("comma", 0),
         "-": ("minus", 0), "=": ("equal", 0), "/": ("slash", 0),
         ";": ("semicolon", 0), "'": ("apostrophe", 0), "!": ("1", 1),
         "?": ("slash", 1), ":": ("semicolon", 1), "\"": ("apostrophe", 1),
         "(": ("9", 1), ")": ("0", 1), "_": ("minus", 1), "+": ("equal", 1)}


def log(msg):
    print(f"[macemu] {msg}", flush=True)


class XImage(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                ("xoffset", ctypes.c_int), ("format", ctypes.c_int),
                ("data", ctypes.POINTER(ctypes.c_ubyte)),
                ("byte_order", ctypes.c_int), ("bitmap_unit", ctypes.c_int),
                ("bitmap_bit_order", ctypes.c_int), ("bitmap_pad", ctypes.c_int),
                ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int),
                ("bits_per_pixel", ctypes.c_int)]


class X11:
    """Just enough Xlib + XTest via ctypes: fake input, read pixels."""

    def __init__(self, display):
        x = self.x = ctypes.CDLL("libX11.so.6")
        t = self.t = ctypes.CDLL("libXtst.so.6")
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XStringToKeysym.restype = ctypes.c_ulong
        x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        x.XKeysymToKeycode.restype = ctypes.c_ubyte
        x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XGetImage.restype = ctypes.POINTER(XImage)
        x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_ulong, ctypes.c_int]
        x.XDestroyImage.argtypes = [ctypes.POINTER(XImage)]
        x.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong)]
        t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                           ctypes.c_int, ctypes.c_ulong]
        t.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_int, ctypes.c_ulong]
        self.dpy = x.XOpenDisplay(display.encode())
        if not self.dpy:
            raise RuntimeError(f"cannot open X display {display}")
        self.root = x.XDefaultRootWindow(self.dpy)

    def origin(self, wid):
        """Root coordinates of the inside of window wid."""
        ox, oy, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        self.x.XTranslateCoordinates(self.dpy, wid, self.root, 0, 0,
                                     ctypes.byref(ox), ctypes.byref(oy),
                                     ctypes.byref(child))
        return ox.value, oy.value

    def motion(self, x, y):
        self.t.XTestFakeMotionEvent(self.dpy, -1, int(x), int(y), 0)
        self.x.XFlush(self.dpy)

    def button(self, down):
        self.t.XTestFakeButtonEvent(self.dpy, 1, int(down), 0)
        self.x.XFlush(self.dpy)

    def key(self, name, down):
        ks = self.x.XStringToKeysym(name.encode())
        kc = self.x.XKeysymToKeycode(self.dpy, ks) if ks else 0
        if not kc:
            raise ValueError(f"unknown key {name!r}")
        self.t.XTestFakeKeyEvent(self.dpy, kc, int(down), 0)
        self.x.XFlush(self.dpy)

    def grab(self, x0, y0, w, h):
        """w*h bytes, one per pixel: 0 = black, 255 = white (32-bit BGRX)."""
        img = self.x.XGetImage(self.dpy, self.root, x0, y0, w, h, 0xFFFFFFFF, 2)
        if not img:
            raise RuntimeError("XGetImage failed")
        im = img.contents
        if im.bits_per_pixel != 32:
            raise RuntimeError(f"unexpected {im.bits_per_pixel} bits per pixel")
        raw = ctypes.string_at(im.data, im.bytes_per_line * h)
        self.x.XDestroyImage(img)
        bpl = im.bytes_per_line         # the Mac screen is pure black and
        return b"".join(raw[r * bpl + 1:r * bpl + 4 * w:4]  # white: take green
                        for r in range(h))

    def close(self):
        self.x.XCloseDisplay(self.dpy)


def write_png(path, pixels, w, h):
    """8-bit grayscale PNG without any library."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    rows = b"".join(b"\0" + pixels[y * w:(y + 1) * w] for y in range(h))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


class Mac:
    def __init__(self, args):
        self.args = args
        self.tmp = tempfile.mkdtemp(prefix="macemu-")
        self.xvfb = self.emu = self.x = None
        self.pos = (MAC_W // 2, MAC_H // 2)

    def start(self):
        n = 90
        while os.path.exists(f"/tmp/.X{n}-lock") or os.path.exists(f"/tmp/.X11-unix/X{n}"):
            n += 1
        self.display = f":{n}"
        xlog = os.path.join(self.tmp, "xvfb.log")
        self.xvfb = subprocess.Popen(["Xvfb", self.display, "-screen", "0", "800x600x24",
                                      "-nolisten", "tcp"],
                                     stdout=subprocess.DEVNULL, stderr=open(xlog, "w"))
        end = time.time() + 30
        while not os.path.exists(f"/tmp/.X11-unix/X{n}"):
            if self.xvfb.poll() is not None or time.time() > end:
                raise RuntimeError("Xvfb did not start: " + open(xlog).read().strip()[-500:])
            time.sleep(0.05)
        time.sleep(0.2)
        self.x = X11(self.display)

        disks = []
        for i, d in enumerate(self.args.disk):
            copy = os.path.join(self.tmp, f"{i}_{os.path.basename(d)}")
            shutil.copyfile(d, copy)
            disks.append(copy)
        env = dict(os.environ, DISPLAY=self.display)
        env.pop("WAYLAND_DISPLAY", None)
        cmd = [self.args.emu, "-r", os.path.abspath(self.args.rom)] + disks
        log("starting " + " ".join(shlex.quote(c) for c in cmd))
        self.emu = subprocess.Popen(cmd, cwd=self.tmp, env=env,
                                    stdout=subprocess.DEVNULL,
                                    stderr=open(os.path.join(self.tmp, "emu.log"), "w"))
        self.find_window(env)
        self.warp(*self.pos)

    def find_window(self, env):
        deadline = time.time() + 15
        while time.time() < deadline:
            wids = []                   # X11 build: titled after its binary
            for sel in (["--name", "^(minivmac|Mini vMac)"], ["--pid", str(self.emu.pid)]):
                r = subprocess.run(["xdotool", "search", "--onlyvisible"] + sel,
                                   env=env, capture_output=True, text=True)
                wids += r.stdout.split()
            for wid in dict.fromkeys(wids):
                g = subprocess.run(["xdotool", "getwindowgeometry", "--shell", wid],
                                   env=env, capture_output=True, text=True).stdout
                d = dict(l.split("=", 1) for l in g.split() if "=" in l)
                w, h = int(d.get("WIDTH", 0)), int(d.get("HEIGHT", 0))
                if w and w % MAC_W == 0 and h == w // MAC_W * MAC_H:
                    self.scale = w // MAC_W
                    self.origin = self.x.origin(int(wid))
                    return
            if self.emu.poll() is not None:
                err = open(os.path.join(self.tmp, "emu.log")).read().strip()
                raise RuntimeError("the emulator quit: " + (err or "no message"))
            time.sleep(0.1)
        raise RuntimeError("the emulator window did not appear")

    def stop(self):
        if self.emu and self.emu.poll() is None:
            self.emu.kill()
            self.emu.wait()
        if self.x:
            self.x.close()
        if self.xvfb:
            self.xvfb.terminate()
            self.xvfb.wait()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- screen
    def screen(self):
        k = self.scale
        x0, y0 = self.origin
        px = self.x.grab(x0, y0, MAC_W * k, MAC_H * k)
        if k == 1:
            return px
        w = MAC_W * k
        return b"".join(px[y * k * w:(y * k + 1) * w][::k] for y in range(MAC_H))

    def menubar(self, px):
        """Menu bar: a white bar with a black line under it (row 19)."""
        line = px[19 * MAC_W:20 * MAC_W]
        top = px[5 * MAC_W:6 * MAC_W]
        return line.count(0) == MAC_W and top[:8].count(255) == 8

    def wait_stable(self, still, timeout):
        end = time.time() + timeout
        last, since = self.screen(), time.time()
        while time.time() < end:
            time.sleep(0.1)
            px = self.screen()
            if px != last:
                last, since = px, time.time()
            elif time.time() - since >= still:
                return True
        return False

    # -- input
    def warp(self, x, y):
        k = self.scale
        self.x.motion(self.origin[0] + x * k + k // 2, self.origin[1] + y * k + k // 2)
        self.pos = (x, y)

    def goto(self, xy):
        if xy:
            self.warp(*xy)
            time.sleep(0.1)

    def click(self, hold=0.08):
        self.x.button(True)
        time.sleep(hold)
        self.x.button(False)

    def tap(self, name, hold=0.08):
        self.x.key(name, True)
        time.sleep(hold)
        self.x.key(name, False)

    def run(self, step):
        words = shlex.split(step)
        verb, args = words[0], [w for w in words[1:] if "=" not in w]
        kw = dict(w.split("=", 1) for w in words[1:] if "=" in w)
        xy = (int(args[0]), int(args[1])) if len(args) >= 2 and verb in (
            "move", "click", "dblclick") else None
        if verb == "boot":
            end = time.time() + float(kw.get("timeout", 90))
            while not self.menubar(self.screen()):
                if time.time() > end:
                    log("boot: no menu bar after the timeout (a program without one?)")
                    return
                time.sleep(0.2)
            self.wait_stable(1.0, 10)
        elif verb == "wait":
            time.sleep(float(args[0]))
        elif verb == "wait_stable":
            if not self.wait_stable(float(kw.get("still", 1.5)), float(kw.get("timeout", 60))):
                log(f"wait_stable: timeout, the screen kept changing")
        elif verb == "wait_change":
            before, end = self.screen(), time.time() + float(kw.get("timeout", 30))
            while self.screen() == before:
                if time.time() > end:
                    log("wait_change: timeout, the screen did not change")
                    break
                time.sleep(0.05)
        elif verb == "shot":
            os.makedirs(self.args.out, exist_ok=True)
            path = os.path.join(self.args.out, args[0].removesuffix(".png") + ".png")
            write_png(path, self.screen(), MAC_W, MAC_H)
            log(f"screenshot {path}")
        elif verb == "move":
            self.goto(xy)
        elif verb == "click":
            self.goto(xy)
            self.click()
        elif verb == "dblclick":
            self.goto(xy)
            self.click(0.06)
            time.sleep(0.1)
            self.click(0.06)
        elif verb == "drag":
            x1, y1, x2, y2 = (int(v) for v in args[:4])
            self.goto((x1, y1))
            self.x.button(True)
            steps = 20
            for i in range(1, steps + 1):
                self.warp(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
                time.sleep(0.02)
            self.x.button(False)
        elif verb == "key":
            for spec in args:
                parts = [MODS.get(p.lower(), p) for p in spec.split("+")]
                for m in parts[:-1]:
                    self.x.key(m, True)
                    time.sleep(0.05)
                self.tap(parts[-1])
                for m in reversed(parts[:-1]):
                    self.x.key(m, False)
                time.sleep(0.1)
        elif verb == "hold":
            keys = [MODS.get(k.lower(), k) for k in args[0].split(",")]
            for k in keys:
                self.x.key(k, True)
            time.sleep(float(args[1]) if len(args) > 1 else 0.5)
            for k in reversed(keys):
                self.x.key(k, False)
        elif verb == "type":
            for ch in " ".join(args):
                ks, shift = CHARS.get(ch, (ch.lower(), ch.isupper()))
                if shift:
                    self.x.key("Shift_L", True)
                self.tap(ks, 0.05)
                if shift:
                    self.x.key("Shift_L", False)
                time.sleep(0.08)
        elif verb == "speed":
            self.x.key("Control_L", True)       # Mini vMac's control mode
            time.sleep(0.15)
            self.tap("s")
            time.sleep(0.1)
            self.tap(SPEED_KEYS[args[0].lower()])
            time.sleep(0.1)
            self.x.key("Control_L", False)
            time.sleep(0.4)
        else:
            raise ValueError(f"unknown step {verb!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("steps", nargs="?", default="boot; shot screen")
    ap.add_argument("--disk", action="append")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "shots"))
    ap.add_argument("--rom", default=os.path.join(ROOT, "mac", "Mac128K.ROM"))
    ap.add_argument("--emu", default=shutil.which("minivmac") or "minivmac")
    args = ap.parse_args()
    args.disk = args.disk or [os.path.join(ROOT, "out", "Test.dsk")]
    steps = args.steps
    if steps.startswith("@"):
        steps = open(steps[1:]).read()
    steps = [s.split("#")[0].strip() for s in steps.replace("\n", ";").split(";")]
    steps = [s for s in steps if s]

    for f, what in ((args.rom, "ROM"), *((d, "disk image") for d in args.disk)):
        if not os.path.isfile(f):
            sys.exit(f"macemu: {what} {f} not found"
                     + (" - see mac/README.md" if what == "ROM" or "Test.dsk" in f else ""))
    if not shutil.which(args.emu):
        sys.exit(f"macemu: emulator {args.emu} not found - run setup/cloud-setup.sh")

    mac = Mac(args)
    try:
        mac.start()
        for step in steps:
            log(step)
            mac.run(step)
    finally:
        mac.stop()


if __name__ == "__main__":
    main()
