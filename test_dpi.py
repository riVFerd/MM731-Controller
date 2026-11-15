"""Check the DPI block codec against real MM731 dongle traffic from captures/. Run: python test_dpi.py"""
import mm731

# Mouse replies to 4A 81 01 0n (captures/2000_to_1200dpi.pcapng)
REPLIES = [bytes.fromhex(h.ljust(128, "0")) for h in (
    "4b84010001ff01000001040006070f7800007f900190",
    "4b010101d007d007b004b00440064006800c800c401f",
    "4b0201401f384a384affff000000ffff00ff00ff0000",
    "4b0301ffffff8000ff00",
)]
# What MasterPlus+ wrote after setting stage 1 to 2000 (captures/800_2000dpi.pcapng)
WRITE_01 = bytes.fromhex("4a010201d007d007b004b00440064006800c800c401f")


class FakeDev:
    def __init__(self):
        self.sent = []

    def xfer(self, buf, want=None, **_):
        self.sent.append(bytes(buf[1:]))
        if buf[1:3] == [0x4A, 0x81]:
            return REPLIES[buf[4]]
        return b""


dev = FakeDev()
fam = mm731.Family712(dev)
p = fam.read_block()
assert mm731.dpi_stages(p) == [(400, 400), (2000, 2000), (1200, 1200), (1600, 1600),
                               (3200, 3200), (8000, 8000), (19000, 19000)], mm731.dpi_stages(p)
assert p[mm731.DPI_ACTIVE] == 1          # 0-based: stage 2 (2000) was active in this capture

dev.sent.clear()
fam.write_block(p)                       # unchanged block must reproduce MasterPlus+'s write
assert dev.sent[2].startswith(WRITE_01), dev.sent[2][:24].hex(" ")
assert dev.sent[-1][:4] == bytes([0x5C, 0x81, 0x02, 0x03])

mm731.set_dpi(p, 6, 1600)                # stage 6 straddles chunks 01 and 02
assert mm731.dpi_stages(p)[5] == (1600, 1600)
assert mm731.dpi_stages(p)[6] == (19000, 19000)
mm731.set_dpi(p, 1, 800)                 # stage 1 straddles chunks 84 and 01
assert mm731.dpi_stages(p)[0] == (800, 800) and mm731.dpi_stages(p)[1] == (2000, 2000)
assert p[mm731.POLL] == mm731.POLL_CODES[1000]    # this capture was taken at 1000 Hz
assert p[mm731.LOD] == mm731.LOD_CODES["low"]

# Button table: MasterPlus+ remapping the DPI button to right click (captures/btn_dpi_to_rightclick.pcapng)
BTN_REPLIES = {0: bytes.fromhex("49820101a500a600a700a900aa00fd15ad01adff".ljust(128, "0")),
               1: bytes.fromhex("4901010000fe00fd2afd200000ad01adff".ljust(128, "0"))}
BTN_WRITE = bytes.fromhex("48820201a500a600a700a900aa00a600ad01adff")


class FakeBtnDev(FakeDev):
    def xfer(self, buf, want=None, **_):
        self.sent.append(bytes(buf[1:]))
        return BTN_REPLIES[buf[4]] if buf[1:4] == [0x48, 0x81, 0x01] else b""


bdev = FakeBtnDev()
bfam = mm731.Family712(bdev)
parts = bfam.read_buttons()
o = 1 + 2 * mm731.BUTTONS.index("dpi")
assert tuple(parts[0][o:o + 2]) == mm731.BTN_FUNCS["dpi-cycle"]
parts[0][o:o + 2] = bytes(mm731.BTN_FUNCS["right"])
bdev.sent.clear()
bfam.write_buttons(parts)
assert bdev.sent[1][:4] == bytes([0x48, 0x81, 0x06, 0x01])
assert bdev.sent[2].startswith(BTN_WRITE), bdev.sent[2][:24].hex(" ")
assert bdev.sent[3].startswith(bytes.fromhex("48010200")), bdev.sent[3][:24].hex(" ")

# Combo layer: middle+forward -> right click (captures/btn_combo-midclic+forward_to_rightclick.pcapng)
s = bytearray().join(bfam.read_buttons())
o = 1 + 2 * mm731.BUTTONS.index("combo-forward")
assert tuple(s[o:o + 2]) == mm731.BTN_FUNCS["led-color"]
assert tuple(s[1 + 2 * mm731.BUTTONS.index("combo-middle"):][:2]) == mm731.BTN_FUNCS["combo-key"]
s[o:o + 2] = bytes(mm731.BTN_FUNCS["right"])
assert bytes(s[mm731.BLOCK_CHUNK:]).startswith(bytes.fromhex("0000fe00fd2aa6000000ad01adff"))
assert mm731.BTN_FUNCS["key:a"] == (0x04, 0) and mm731.BTN_FUNCS["key:1"] == (0x1E, 0)
assert mm731.BTN_FUNCS["key:0"] == (0x27, 0) and mm731.BTN_FUNCS["key:alt"] == (0xE2, 0)
print("ok")
