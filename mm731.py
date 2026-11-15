#!/usr/bin/env python3
"""
mm731.py - tiny open-source controller prototype for the Cooler Master MM731.

The MM731 (USB VID 0x2516, PID 0x0167 when wired) is NOT supported by OpenRGB yet.
Its two closest relatives ARE, and they speak two different protocol "families":

  * "730" family - MM730 (PID 0x0165, wired twin of the MM731), MM711, MM720.
                   Vendor interface 1, usage page 0xFF00. Commands 0x41/0x50/0x51/0x52.
  * "712" family - MM712 (PID 0x0169, tri-mode wireless like the MM731).
                   Vendor interface 3, usage page 0xFF0A. Commands 0x44/0x4C/0x54/0x5A.

We don't know yet which one the MM731 speaks, so `probe` sends only READ-ONLY
queries from both families and shows what answers. Once you know the family,
`color` / `mode` send lighting changes. Nothing is written to the mouse's flash
unless you pass --save.

Packet layouts are taken from OpenRGB (GPL-2.0-or-later):
  Controllers/CoolerMasterController/CMMMController   (730 family)
  Controllers/CoolerMasterController/CMMM712Controller (712 family, MM712protocol.txt)

Requires:  pip install hidapi      (provides `import hid`)
Close MasterPlus+ before running - it holds the device open.
"""

import argparse
import sys
import time

try:
    import hid
except ImportError:
    sys.exit("Missing dependency: pip install hidapi")

VID = 0x2516
KNOWN_PIDS = {
    0x0167: "MM731 (wired, PID from OpenRGB issue #1937)",
    0x0165: "MM730",
    0x0169: "MM712",
}
PACKET = 65          # 1 report-ID byte (0x00) + 64 data bytes
TIMEOUT_MS = 250

# ---------------------------------------------------------------- low level

def hexs(data):
    return " ".join(f"{b:02x}" for b in data)


def pkt(*head, fill=0x00):
    """Build a 65-byte output report: leading 0x00 report ID + payload, padded."""
    buf = [0x00] + list(head)
    buf += [fill] * (PACKET - len(buf))
    return buf


class Dev:
    def __init__(self, path, dry_run=False, verbose=True):
        self.dry = dry_run
        self.verbose = verbose
        self.path = path
        self.h = None
        if not dry_run:
            self.h = hid.device()
            self.h.open_path(path)

    def xfer(self, buf, expect_reply=True, read_only=False, want=None):
        """read_only packets are sent even in dry-run; want = reply prefix to wait for,
        skipping unsolicited status reports (47 81 70 ...) that share the pipe."""
        if self.verbose:
            print(f"  -> {hexs(buf[1:24])} ...")
        if self.dry and not read_only:
            return b""
        if self.h is None:
            self.h = hid.device()
            self.h.open_path(self.path)
        self.h.write(buf)
        if not expect_reply:
            return b""
        resent = False
        for _ in range(8):
            r = bytes(self.h.read(PACKET - 1, TIMEOUT_MS))
            if not r and want is not None and not resent:
                self.h.write(buf)          # a sleeping wireless mouse drops the first request
                resent = True
                continue
            if want is None or r[:len(want)] == bytes(want) or not r:
                break
        if self.verbose:
            print(f"  <- {hexs(r[:24]) if r else '(no reply)'}")
        if want is not None and r[:len(want)] != bytes(want):
            raise OSError(f"expected reply {hexs(want)}, got {hexs(r[:8]) or 'nothing'}")
        return r

    def close(self):
        if self.h:
            self.h.close()

# ---------------------------------------------------------------- protocols

class Family730:
    """MM730 / MM711 / MM720 protocol (CMMMController in OpenRGB)."""
    name = "730"
    CMD = 0x2B                        # CM_MM7XX_COMMAND
    MODES = {"static": 0, "breathing": 1, "cycle": 2, "stars": 3,
             "indicator": 4, "off": 254}
    SPEEDS = [0x3C, 0x37, 0x31, 0x2C, 0x26]   # 1 (slow) .. 5 (fast)

    def __init__(self, dev):
        self.d = dev

    def init(self):
        return self.d.xfer(pkt(0x41, 0x80))

    def query(self):
        """Read-only status queries."""
        self.init()
        return {
            "colour": self.d.xfer(pkt(0x52, self.CMD)),
            "mode":   self.d.xfer(pkt(0x52, 0x28)),
        }

    def set(self, mode, r=255, g=255, b=255, brightness=255, speed=3):
        m = self.MODES[mode]
        self.init()
        self.d.xfer(pkt(0x51, 0x28, 0x00, 0x00, m))          # apply/select mode
        if m == self.MODES["off"]:
            return
        nfi1 = 0x00 if m in (0, 2) else 0x20
        body = [0x51, self.CMD, 0x00, 0x00, m, self.SPEEDS[speed - 1], nfi1,
                0xFF, 0xFF, brightness, r, g, b, 0x00, 0x00, 0x00]
        buf = pkt(*body)
        for i in range(17, PACKET):
            buf[i] = 0xFF
        self.d.xfer(buf)

    def save(self):
        self.d.xfer(pkt(0x50, 0x55))


class Family712:
    """MM712 protocol (CMMM712Controller / MM712protocol.txt in OpenRGB)."""
    name = "712"
    MODES = {"static": 0, "breathing": 1, "cycle": 2, "off": 3}
    SPEEDS = [0x00, 0x01, 0x02, 0x03, 0x04]   # observed 0x02..0x04; adjust after testing

    def __init__(self, dev):
        self.d = dev

    def init(self):
        return self.d.xfer(pkt(0x44, 0x81, 0x02))

    def query(self):
        self.init()
        out = {"mode": self.d.xfer(pkt(0x4C, 0x81, 0x07))}
        for m in (0, 1, 2):
            out[f"colour[mode {m}]"] = self.d.xfer(pkt(0x4C, 0x81, 0x03, m))
        return out

    def set(self, mode, r=255, g=255, b=255, brightness=255, speed=3):
        m = self.MODES[mode]
        self.init()
        if mode != "off":
            # 0xFF = use the RGB below; 0x06 (factory default) shows the preset CM purple instead
            self.d.xfer(pkt(0x4C, 0x81, 0x04, m, 0xFF, brightness,
                            self.SPEEDS[speed - 1], r, g, b, 0xFF))
        # The mouse sometimes ignores the mode switch right after the colour write: verify and resend.
        for _ in range(4):
            self.d.xfer(pkt(0x4C, 0x81, 0x08, m))
            if self.d.dry:
                break
            time.sleep(0.05)
            if self.d.xfer(pkt(0x4C, 0x81, 0x07), read_only=True, want=(0x4D, 0x81, 0x07))[3] == m:
                break
        else:
            raise OSError(f"mouse did not switch to lighting mode {mode}")

    def save(self):
        self.d.xfer(pkt(0x54, 0x81, 0x01))

    def read_lighting(self):
        """-> (active mode, {mode: (brightness, speed byte, (r, g, b))}) for modes 0-2."""
        self.d.xfer(pkt(0x44, 0x81, 0x02), read_only=True)
        mode = self.d.xfer(pkt(0x4C, 0x81, 0x07), read_only=True, want=(0x4D, 0x81, 0x07))[3]
        per = {}
        for m in (0, 1, 2):
            r = self.d.xfer(pkt(0x4C, 0x81, 0x03, m), read_only=True, want=(0x4D, 0x81, 0x03))
            per[m] = (r[4], r[5], tuple(r[6:9]))
        return mode, per

    # Settings block (decoded from MasterPlus+ captures on the MM731 dongle):
    # read  4A 81 01 0n      -> reply 4B <chunk> 01 <19 payload bytes>, chunk = 84,01,02,03
    # write 4A <chunk> 02 <19 payload bytes> for all 4 chunks, then 5C 81 02 03 (apply).
    CHUNKS = (0x84, 0x01, 0x02, 0x03)

    def read_block(self):
        self.d.xfer(pkt(0x44, 0x81, 0x02), read_only=True)
        payload = bytearray()
        for n, c in enumerate(self.CHUNKS):
            r = self.d.xfer(pkt(0x4A, 0x81, 0x01, n), read_only=True, want=(0x4B, c))
            payload += r[3:3 + BLOCK_CHUNK]
        return payload

    def write_block(self, payload):
        self.d.xfer(pkt(0x44, 0x81, 0x02))
        for n, c in enumerate(self.CHUNKS):
            part = payload[n * BLOCK_CHUNK:(n + 1) * BLOCK_CHUNK]
            self.d.xfer(pkt(0x4A, c, 0x02, *part))
        self.d.xfer(pkt(0x5C, 0x81, 0x02, 0x03))

    # Button table (captures/btn_*.pcapng): read 48 81 01 0n -> 49 <82|01> 01 <payload>;
    # write 48 81 06 01, then 48 82 02 <payload0>, 48 01 02 <payload1>.
    BTN_CHUNKS = (0x82, 0x01)

    def read_buttons(self):
        self.d.xfer(pkt(0x44, 0x81, 0x02), read_only=True)
        return [bytearray(self.d.xfer(pkt(0x48, 0x81, 0x01, n), read_only=True, want=(0x49, c))[3:3 + BLOCK_CHUNK])
                for n, c in enumerate(self.BTN_CHUNKS)]

    def write_buttons(self, parts):
        self.d.xfer(pkt(0x44, 0x81, 0x02))
        self.d.xfer(pkt(0x48, 0x81, 0x06, 0x01))
        for c, part in zip(self.BTN_CHUNKS, parts):
            self.d.xfer(pkt(0x48, c, 0x02, *part))


# Settings-block payload layout (4 chunks x 19 bytes, concatenated)
BLOCK_CHUNK = 19
DPI_ACTIVE = 1            # active DPI stage, 0-based in the payload (DPI button cycles 0..6)
DPI_TABLE = 16            # stage k (0-based): X at 16+4k, Y at 18+4k, little-endian u16
DPI_STAGES = 7
DPI_MIN, DPI_MAX, DPI_STEP = 100, 19000, 100   # ponytail: MM731 spec range; MasterPlus+ moves in 100s


LOD = 0                   # lift-off distance (captures/lod_*.pcapng)
LOD_CODES = {"low": 0x00, "high": 0x02}
POLL = 7                 # polling-rate code (captures/*hz*.pcapng)
POLL_CODES = {125: 0x01, 250: 0x02, 500: 0x03, 1000: 0x04}   # ponytail: 250 Hz inferred, not captured


# Button table payload0: [01] then one 2-byte code per button, in this order.
# ponytail: side-button names (back/forward) guessed from HID button order; swap if reversed.
# Both chunks form one stream; slot i at stream[1+2i]. Slots 8-15 = combo layer (hold middle + button).
_BASE = ["left", "right", "middle", "back", "forward", "dpi", "wheel-up", "wheel-down"]
BUTTONS = _BASE + ["combo-" + b for b in _BASE]
BTN_FUNCS = {"none": (0x00, 0x00), "left": (0xA5, 0x00), "right": (0xA6, 0x00), "middle": (0xA7, 0x00),
             "back": (0xA9, 0x00), "forward": (0xAA, 0x00), "dpi-cycle": (0xFD, 0x15),
             "scroll-up": (0xAD, 0x01), "scroll-down": (0xAD, 0xFF), "play-pause": (0xEC, 0x00),
             # found by testing on the MM731 (MasterPlus+ doesn't offer these)
             "volume-up": (0xE8, 0x00), "volume-down": (0xE9, 0x00), "mute": (0xEA, 0x00),
             "stop": (0xEB, 0x00), "next-track": (0xED, 0x00), "prev-track": (0xEE, 0x00),
             "led-mode": (0xFD, 0x2A), "led-color": (0xFD, 0x20), "combo-key": (0xFE, 0x00)}


# Keyboard keys map directly as `<HID usage> 00` (verified: 04=a, 05=b, 1e=1, e2=alt).
KEYS = {**{chr(ord("a") + i): 0x04 + i for i in range(26)},
        **{str((i + 1) % 10): 0x1E + i for i in range(10)},
        **{f"f{i + 1}": 0x3A + i for i in range(12)},
        "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "printscreen": 0x46, "insert": 0x49, "home": 0x4A, "pageup": 0x4B, "delete": 0x4C,
        "end": 0x4D, "pagedown": 0x4E, "right-arrow": 0x4F, "left-arrow": 0x50,
        "down-arrow": 0x51, "up-arrow": 0x52,
        "ctrl": 0xE0, "shift": 0xE1, "alt": 0xE2, "win": 0xE3}
BTN_FUNCS.update({f"key:{k}": (v, 0x00) for k, v in KEYS.items()})


def dpi_stages(p):
    return [(int.from_bytes(p[DPI_TABLE + 4 * k:DPI_TABLE + 4 * k + 2], "little"),
             int.from_bytes(p[DPI_TABLE + 4 * k + 2:DPI_TABLE + 4 * k + 4], "little"))
            for k in range(DPI_STAGES)]


def set_dpi(p, stage, value):
    """Set both X and Y of a 1-based stage."""
    o = DPI_TABLE + 4 * (stage - 1)
    p[o:o + 4] = value.to_bytes(2, "little") * 2


FAMILIES = {"730": Family730, "712": Family712}

# ---------------------------------------------------------------- discovery

def vendor_interfaces(pid=None):
    """All Cooler Master HID interfaces on a vendor-defined usage page (>= 0xFF00)."""
    out = []
    for d in hid.enumerate(VID, pid or 0):
        if d.get("usage_page", 0) >= 0xFF00:
            out.append(d)
    return out


def describe(d):
    pid = d["product_id"]
    return (f"PID 0x{pid:04x} {KNOWN_PIDS.get(pid, '(unknown PID)')} | "
            f"iface {d.get('interface_number')} | usage_page 0x{d.get('usage_page', 0):04x} "
            f"usage 0x{d.get('usage', 0):04x} | {d.get('product_string')}")


def pick(args):
    """Choose the HID interface to talk to."""
    cands = vendor_interfaces(args.pid)
    if args.interface is not None:
        cands = [d for d in cands if d.get("interface_number") == args.interface]
    if args.usage_page is not None:
        cands = [d for d in cands if d.get("usage_page") == args.usage_page]
    if not cands:
        sys.exit("No matching Cooler Master vendor interface found. Run `list` first.")
    if len(cands) > 1:
        print("Several interfaces match; using the first. Narrow with --interface/--usage-page:")
        for d in cands:
            print("   ", describe(d))
    return cands[0]

# ---------------------------------------------------------------- commands

def cmd_list(args):
    devs = list(hid.enumerate(VID, 0))
    if not devs:
        print("No Cooler Master (VID 0x2516) HID devices found.")
        print("Plug the mouse in with the cable first; the wireless dongle may use another PID.")
        return
    for d in devs:
        tag = "  <- vendor interface (config channel candidate)" if d.get("usage_page", 0) >= 0xFF00 else ""
        print(describe(d) + tag)


def cmd_probe(args):
    """Send read-only queries from both families to every vendor interface."""
    cands = vendor_interfaces(args.pid)
    if not cands:
        sys.exit("No vendor interfaces found. Run `list`.")
    for d in cands:
        print("\n=== " + describe(d))
        for fam_name, Fam in FAMILIES.items():
            print(f"  [{fam_name} family, read-only]")
            try:
                dev = Dev(d["path"])
            except OSError as e:
                print(f"  could not open: {e} (is MasterPlus+ still running?)")
                break
            try:
                res = Fam(dev).query()
                answered = any(res.values())
                print(f"  => {'GOT REPLIES' if answered else 'no replies'}")
            except OSError as e:
                print(f"  error: {e}")
            finally:
                dev.close()
            time.sleep(0.1)
    print("\nThe family + interface that GOT REPLIES (with replies that echo the "
          "command byte, e.g. 0x4d for a 0x4c query or 0x52 for a 0x52 query) is your channel.")


def run_set(args, mode):
    d = pick(args)
    print("Using:", describe(d))
    dev = Dev(d["path"], dry_run=args.dry_run)
    try:
        fam = FAMILIES[args.family](dev)
        r, g, b = parse_rgb(args.rgb) if getattr(args, "rgb", None) else (255, 255, 255)
        fam.set(mode, r, g, b, brightness=args.brightness, speed=args.speed)
        if args.save:
            print("Saving to onboard flash...")
            fam.save()
    finally:
        dev.close()


def cmd_color(args):
    run_set(args, args.mode)


def cmd_off(args):
    run_set(args, "off")


def cmd_raw(args):
    """Send an arbitrary packet (hex bytes after the report ID). For experiments."""
    d = pick(args)
    print("Using:", describe(d))
    payload = [int(x, 16) for x in args.bytes]
    dev = Dev(d["path"], dry_run=args.dry_run)
    try:
        dev.xfer(pkt(*payload))
    finally:
        dev.close()


def cmd_dpi(args):
    """Show DPI stages, or change a stage value / the active stage (712 family only)."""
    if args.family != "712":
        sys.exit("dpi is only decoded for --family 712")
    if args.value is not None and args.stage is None:
        sys.exit("--value needs --stage")
    if args.value is not None and not (DPI_MIN <= args.value <= DPI_MAX and args.value % DPI_STEP == 0):
        sys.exit(f"--value must be {DPI_MIN}-{DPI_MAX} in steps of {DPI_STEP}")
    def change(p):
        if args.value is not None:
            set_dpi(p, args.stage, args.value)
        if args.active is not None:
            p[DPI_ACTIVE] = args.active - 1

    def show(p):
        for k, (x, y) in enumerate(dpi_stages(p), 1):
            mark = " <- active" if k == p[DPI_ACTIVE] + 1 else ""
            print(f"  stage {k}: {x}" + (f" x {y}" if x != y else "") + mark)

    edit_block(args, change, show, args.value is not None or args.active is not None)


def cmd_poll(args):
    """Show or set the polling rate (712 family only)."""
    if args.family != "712":
        sys.exit("poll is only decoded for --family 712")

    def change(p):
        if args.hz is not None:
            p[POLL] = POLL_CODES[args.hz]

    def show(p):
        hz = {v: k for k, v in POLL_CODES.items()}.get(p[POLL])
        print(f"  polling rate: {hz} Hz" if hz else f"  polling rate: unknown code 0x{p[POLL]:02x}")

    edit_block(args, change, show, args.hz is not None)


def cmd_lod(args):
    """Show or set lift-off distance (712 family only)."""
    if args.family != "712":
        sys.exit("lod is only decoded for --family 712")

    def change(p):
        if args.level is not None:
            p[LOD] = LOD_CODES[args.level]

    def show(p):
        name = {v: k for k, v in LOD_CODES.items()}.get(p[LOD])
        print(f"  lift-off distance: {name}" if name else f"  lift-off distance: unknown code 0x{p[LOD]:02x}")

    edit_block(args, change, show, args.level is not None)


def cmd_button(args):
    """Show the button map, or remap one button to a mouse function (712 family only)."""
    if args.family != "712":
        sys.exit("button is only decoded for --family 712")
    if args.name == "left" and args.func not in (None, "left"):
        sys.exit("Refusing to remap left click (you'd lose the ability to click).")
    if args.name == "combo-middle" and args.func not in (None, "combo-key"):
        sys.exit("combo-middle is the combo key itself; remapping it would disable the combo layer.")
    d = pick(args)
    print("Using:", describe(d))
    dev = Dev(d["path"], dry_run=args.dry_run)
    try:
        fam = Family712(dev)
        s = bytearray().join(fam.read_buttons())
        old = bytes(s)
        if args.func:
            o = 1 + 2 * BUTTONS.index(args.name)
            s[o:o + 2] = bytes(BTN_FUNCS[args.func]) if args.func in BTN_FUNCS else bytes.fromhex(args.func)
        names = {v: k for k, v in BTN_FUNCS.items()}
        for i, b in enumerate(BUTTONS):
            code = tuple(s[1 + 2 * i:3 + 2 * i])
            label = names.get(code) or (f"macro {code[1]}" if code[0] == 0xFF else f"code {bytes(code).hex(' ')}")
            print(f"  {b:17} -> {label}")
        if bytes(s) == old:
            if args.func:
                print("Already set; nothing to write.")
            return
        fam.write_buttons([s[:BLOCK_CHUNK], s[BLOCK_CHUNK:]])
        if args.save:
            print("Saving to onboard flash...")
            fam.save()
    finally:
        dev.close()


def edit_block(args, change, show, wants_change):
    """Read the settings block, apply change(), print it, and write back only if it differs."""
    d = pick(args)
    print("Using:", describe(d))
    dev = Dev(d["path"], dry_run=args.dry_run)
    try:
        fam = Family712(dev)
        p = fam.read_block()
        old = bytes(p)
        change(p)
        show(p)
        if bytes(p) == old:
            if wants_change:
                print("Already set; nothing to write.")
            return
        fam.write_block(p)
        if args.save:
            print("Saving to onboard flash...")
            fam.save()
    finally:
        dev.close()


def btn_func(s):
    s = s.lower()
    if s in BTN_FUNCS:
        return s
    if len(s) == 4 and all(c in "0123456789abcdef" for c in s) and s[:2] != "ff":
        return s                                   # ff NN = macro slot; not raw-settable
    raise argparse.ArgumentTypeError(f"unknown function {s!r}")


def parse_rgb(s):
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("colour must be RRGGBB hex, e.g. ff0000")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def main():
    p = argparse.ArgumentParser(description="Cooler Master MM731 control prototype")
    p.add_argument("--pid", type=lambda x: int(x, 16), default=None,
                   help="USB product ID in hex (default: any Cooler Master device)")
    p.add_argument("--interface", type=int, default=None, help="HID interface number")
    p.add_argument("--usage-page", type=lambda x: int(x, 16), default=None,
                   help="HID usage page in hex, e.g. ff00 or ff0a")
    p.add_argument("--family", choices=FAMILIES, default="730",
                   help="protocol family found by `probe` (default 730)")
    p.add_argument("--dry-run", action="store_true", help="print packets, send nothing")
    p.add_argument("--save", action="store_true", help="also write the setting to onboard flash")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list Cooler Master HID interfaces").set_defaults(fn=cmd_list)
    sub.add_parser("probe", help="read-only test of both protocol families").set_defaults(fn=cmd_probe)

    c = sub.add_parser("color", help="set logo lighting")
    c.add_argument("rgb", nargs="?", default="ffffff", help="RRGGBB hex (default ffffff)")
    c.add_argument("--mode", default="static", choices=["static", "breathing", "cycle"])
    c.add_argument("--brightness", type=int, default=255, choices=range(0, 256), metavar="0-255")
    c.add_argument("--speed", type=int, default=3, choices=range(1, 6), metavar="1-5")
    c.set_defaults(fn=cmd_color)

    o = sub.add_parser("off", help="turn logo lighting off")
    o.set_defaults(fn=cmd_off, brightness=0, speed=3, rgb=None)

    dp = sub.add_parser("dpi", help="show DPI stages, or set one: dpi --stage 1 --value 1600")
    dp.add_argument("--stage", type=int, choices=range(1, DPI_STAGES + 1), metavar=f"1-{DPI_STAGES}")
    dp.add_argument("--value", type=int, help=f"DPI {DPI_MIN}-{DPI_MAX}, steps of {DPI_STEP}")
    dp.add_argument("--active", type=int, choices=range(1, DPI_STAGES + 1), metavar=f"1-{DPI_STAGES}",
                    help="make this stage the active one")
    dp.set_defaults(fn=cmd_dpi)

    pl = sub.add_parser("poll", help="show polling rate, or set it: poll 1000")
    pl.add_argument("hz", nargs="?", type=int, choices=sorted(POLL_CODES))
    pl.set_defaults(fn=cmd_poll)

    lo = sub.add_parser("lod", help="show lift-off distance, or set it: lod high")
    lo.add_argument("level", nargs="?", choices=sorted(LOD_CODES))
    lo.set_defaults(fn=cmd_lod)

    bt = sub.add_parser("button", help="show button map, or remap: button dpi right")
    bt.add_argument("name", nargs="?", choices=BUTTONS)
    bt.add_argument("func", nargs="?", type=btn_func, metavar="FUNC",
                    help=f"one of {', '.join(sorted(k for k in BTN_FUNCS if not k.startswith('key:')))}, "
                         "key:<name> (a-z, 0-9, f1-f12, enter, esc, space, ctrl, shift, alt, win, arrows...), "
                         "or a raw 2-byte hex code like ea00")
    bt.set_defaults(fn=cmd_button)

    r = sub.add_parser("raw", help="send raw hex bytes, e.g.: raw 52 28")
    r.add_argument("bytes", nargs="+")
    r.set_defaults(fn=cmd_raw)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
