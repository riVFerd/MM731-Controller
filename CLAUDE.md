# MM731 control tool: project context

## Goal
Replace Cooler Master MasterPlus+, which keeps crashing and freezing, with a small, reliable tool of our own. It only needs to control **one mouse: the Cooler Master MM731**. Python + hidapi. The user runs Windows.

## What's known
- MM731 USB IDs: VID `0x2516`, PID `0x0167` (wired; from OpenRGB issue #1937). 2.4 GHz dongle: PID `0x01b7` ("Cooler Master Mice Dongle"), vendor interfaces 3 and 4 on usage page `0xFF0A` (confirmed 2026-11-15).
- **Dongle speaks the 712 family** (confirmed by `probe`): `44 81 02` -> `45 81 02 00 01`, `4C 81 07` -> `4D 81 07 03`, `4C 81 03 0n` -> `4D 81 03 06 ...` (clean cmd+1 echoes). 730-family replies there were stale buffer contents, not real answers.
- **Lighting verified on the real mouse (dongle, 2026-11-15)**: static, breathing (speed 1 vs 5 visibly differ), cycle, off, brightness all work via `4C 81 04 <mode> <src> <bright> <speed> R G B FF` then `4C 81 08 <mode>`. `<src>` must be `FF` for custom RGB; the factory value `06` ignores RGB and shows the preset CM purple. Readback `4C 81 03 <mode>` returns `<src> <bright> <speed> R G B FF`. Unsolicited `47 81 70 ...` status reports arrive on the same pipe (byte 16 ≈ active mode, byte 17 = src) and can be read in place of a command echo.
- **DPI verified on the real mouse (dongle, 2026-11-15)**, decoded from `captures/*.pcapng`. Settings block = 4 chunks × 19 payload bytes. Read `4A 81 01 0n` → `4B <84|01|02|03> 01 <payload>`; write `4A <chunk> 02 <payload>` ×4, then `5C 81 02 03` (apply). Payload[1] = active stage (0-based); **7 stages**, stage k (0-based) X/Y as LE u16 at payload[16+4k], [18+4k] (stages 1 and 6 straddle chunks). Matches MasterPlus+: 400/2000/800/1600/3200/8000/19000, stage 3 (800) active. Changes apply live but revert on power cycle unless `54 81 01` (save) follows. MasterPlus+ saves on every slider step. `mm731.py dpi` does read-modify-write; `test_dpi.py` checks it against captured bytes.
- **OpenRGB does not support the MM731.** Two close relatives are supported, and they use two different protocol families:
  - **730 family**: MM730 (PID `0x0165`, the MM731's wired twin), MM711, MM720. Vendor interface 1, usage page `0xFF00`. Init `41 80`, read `52 xx`, write `51 xx`, save `50 55`. Source: OpenRGB `Controllers/CoolerMasterController/CMMMController`.
  - **712 family**: MM712 (PID `0x0169`, tri-mode wireless). Interface 3, usage page `0xFF0A`. Init `44 81 02`, cmd `4C 81 xx`, save `54 81 01`, direct `5A 81 xx`. Source: OpenRGB `CMMM712Controller` + `MM712protocol.txt`.
- Packets: the dongle's vendor interfaces (3 and 4) declare **32-byte** input/output reports, no report ID. hidapi on Windows tolerates our 65-byte writes, but WebHID requires exactly 32. All commands fit in 22 bytes.
- OpenRGB issue #1937 has MM731 USB captures (red, green, blue, off, brightness, breathing, cycle) attached as `.pcapng` files. Nobody has decoded them yet. Download them in a browser if needed.
- OpenRGB only covers lighting. DPI, polling rate, lift-off distance, button remapping and macros must be decoded from our own USBPcap captures of MasterPlus+.

## Files
- `mm731.py`: CLI with `list`, `probe` (read-only queries in both families), `color`, `off`, `raw`. Flags: `--family 730|712`, `--interface`, `--usage-page`, `--pid`, `--dry-run`, `--save`.
- `capdiff.py`: extracts host-to-device packets from `.pcapng` files with tshark and diffs two captures byte by byte.
- `mm731.html`: **the main app.** Single-file WebHID page (Chrome/Edge, no install): clickable SVG mouse for remapping (combo layer, media keys, keyboard keys, movable combo key), lighting with live LED preview, 7 DPI stages, polling, lift-off. Apply = live, Save to mouse = flash. JS port of the protocol; keep it in sync with `mm731.py`. Verified on the mouse by the user.
- The tkinter desktop app was removed (2026-11-15); the user chose the webpage only.
- `test_dpi.py`: offline checks of the block/button codecs against captured bytes.
- `README.md`: user-facing guide for the webpage. `DEVELOPMENT.md`: the old CLI/decoding guide (renamed from the prototype README).
- Wireless mouse sleeps when idle and drops the first request; `Dev.xfer` resends once on an empty read.
- The LED mode switch (`4C 81 08 <mode>`) is sometimes ignored right after the colour write; `Family712.set` re-reads `4C 81 07` and resends until it sticks.

## Status
- Roadmap steps 1–2 done over the dongle: 712 family on iface 3, lighting verified (not yet saved to flash with `--save`). Venv at `.venv`.
- DPI stages + active stage done (`dpi` command). Dongle is on USBPcap5. tshark lives in `C:\Program Files\Wireshark` (not on PATH).
- Polling rate decoded: payload[7], `01`=125, `03`=500, `04`=1000 Hz (`02`=250 inferred). `poll` command read and write verified on the mouse (125 Hz felt choppy, back to 1000).
- User's saved default (2026-11-15): stage 2 = 800 DPI, active; 1000 Hz. Save acks with `55 81 01`.
- Lift-off distance decoded and verified by feel: payload[0], `00`=low, `02`=high (`01` not captured). `lod` command. User's saved default: low.
- **Buttons decoded** (`captures/btn_*.pcapng`): read `48 81 01 0n` → `49 <82|01> 01 <19 bytes>`; write `48 81 06 01`, `48 82 02 <p0>`, `48 01 02 <p1>`. p0+p1 = one stream, slot i code at [1+2i]: slots 0-7 = left,right,middle,back,forward,dpi,wheel-up,wheel-down; slots 8-15 = combo layer (hold middle). Codes: a5/a6/a7/a9/aa 00 = mouse buttons, fd 15 DPI cycle, ad 01/ff scroll, ec 00 play/pause, fd 2a LED mode, fd 20 LED colour, fe 00 combo key, 00 00 none, ff NN = macro NN. Keyboard keys are macros (`50 81 05 ff` clear, 36× `4E xx 02 <slot>` chunks full of MasterPlus+ heap garbage, `48 81 04 <slot idx> ff <macro>`): not implemented. `50 81 02 ff` = reset buttons to default (seen, not used). DPI→middle verified live; `button` command.
- Media codes found by live testing (MasterPlus+ only offers play/pause): e8 volume up, e9 volume down, ea mute, eb stop, ec play/pause, ed next track, ee previous track; e2 acted as Alt (other codes near e2 may be modifier keys). `button` accepts raw hex codes (e.g. `e800`) for this kind of probing. Combo middle+DPI works even though MasterPlus+ hides it.
- User's saved layout (2026-11-15): DPI = dpi-cycle; combos (hold middle): +left = prev track, +right = next track, +back = volume down, +forward = volume up, +DPI = play/pause.
- **Keyboard keys map directly** as `<HID usage> 00` (verified live: 04=a, 05=b, 1e=1, e2=Alt), no macro needed. `button <slot> key:<name>`. Second byte is probably a modifier mask (untested), which would give Ctrl+C style shortcuts.
- Next step (optional): find volume-up / previous-track codes, keyboard-key macros, Bluetooth check, GUI/tray app.

## Roadmap
1. Confirm the protocol family and interface from the `probe` output.
2. Verify lighting (color, breathing, cycle, off, brightness, speed). Fix the speed and brightness mappings if needed.
3. Capture and decode DPI stages and polling rate first, then lift-off distance, then buttons and macros.
4. Check behaviour over the 2.4 GHz dongle and Bluetooth (they may differ from wired).
5. Optional: a small GUI or tray app once the commands are stable.

## Rules
- **Never** replay or craft packets from a firmware update. Bricking risk.
- Try every new command with `--dry-run` first, and use `--save` (writes to onboard flash) only once a command is verified.
- Change one setting per capture when decoding.
