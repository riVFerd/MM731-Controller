# Development notes: the `mm731.py` command-line tool

This was the original prototype guide, kept for decoding new settings. Everyday use is the webpage described in [README.md](README.md).

> **Out of date in places.** The MM731 turned out to speak the **712 family** on **interface 3** (dongle PID `0x01b7`), so the examples below that use `--family 730 --interface 1` should read `--family 712 --interface 3 --pid 0x01b7`. The CLI now also has `dpi`, `poll`, `lod` and `button` commands. The decoded protocol is documented in `CLAUDE.md`, and `test_dpi.py` checks it against the captures in `captures/`.

## Setup (Windows)

```
pip install hidapi
```

**Fully quit MasterPlus+ first**, including its tray icon. It holds the mouse open. Plug the mouse in with the **USB cable** for now.

## Step 1: find the right channel

```
python mm731.py list
python mm731.py probe
```

`list` shows every Cooler Master HID interface. The ones marked "vendor interface" are where settings go.

`probe` sends **read-only** status queries in both known Cooler Master mouse protocols:

| family | used by | interface / usage page | a real reply starts with |
|---|---|---|---|
| `730` | MM730 (the MM731's wired twin), MM711, MM720 | 1 / `0xFF00` | `52 ...` for a `52` query |
| `712` | MM712 (tri-mode wireless) | 3 / `0xFF0A` | `4d 81 ...` for a `4c 81` query |

Send me the full `probe` output and I'll tell you which family the mouse speaks.

## Step 2: lighting

Always try `--dry-run` first. It prints the packets without sending them.

```
python mm731.py --family 730 --interface 1 --dry-run color ff0000
python mm731.py --family 730 --interface 1 color ff0000
python mm731.py --family 730 --interface 1 color 00ffff --mode breathing --speed 4
python mm731.py --family 730 --interface 1 off
```

Changes are temporary by default. Add `--save` to write them to the mouse's onboard flash.

## Step 3: decode DPI, polling and buttons

OpenRGB only covers lighting. For everything else, record what MasterPlus+ sends:

1. Install Wireshark and tick **USBPcap** during setup.
2. Capture on the USBPcap hub the mouse is on. Change **one** setting in MasterPlus+, then stop. Save it as, say, `dpi_800.pcapng`.
3. Repeat with one other value, for example `dpi_1600.pcapng`.
4. Run `python capdiff.py dpi_800.pcapng dpi_1600.pcapng`.

The bytes that changed are the setting. Once the pattern is clear, test it with `mm731.py raw <hex bytes>` and then add a real command for it.

## Safety

- Never replay packets captured during a **firmware update**.
- Read-only queries and lighting changes are low risk. A mouse normally ignores packets it doesn't understand.
- If the mouse ever acts strangely, unplug it and plug it back in. Changes made without `--save` don't survive that.

Packet layouts come from OpenRGB (GPL-2.0-or-later): `CMMMController` and `CMMM712Controller`.
