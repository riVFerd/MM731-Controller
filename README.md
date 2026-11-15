# MM731 Control

A small webpage that replaces Cooler Master MasterPlus+ for the **Cooler Master MM731** mouse. It runs in your browser, needs nothing installed, and talks to the mouse directly over USB.

It also unlocks a few things MasterPlus+ doesn't offer: media keys (volume, next/previous track, stop, mute), a combo action on the DPI button, and moving the combo key to any button.

## What you can change

- **Buttons:** every button, plus a second "combo" action for each one that fires while you hold the combo key. Choose mouse clicks, DPI cycle, media keys, LED controls or keyboard keys (letters, numbers, F1–F12, arrows, Ctrl, Shift, Alt, Win and more).
- **Lighting:** static, breathing, colour cycle or off, with colour, brightness and speed.
- **Sensitivity:** all 7 DPI stages and which one the mouse starts on.
- **Polling rate:** 125, 250, 500 or 1000 Hz.
- **Lift-off distance:** low or high.

## How to use it

1. **Quit MasterPlus+ completely**, including its icon in the system tray. While it runs, the mouse ignores everything else.
2. Open **<https://mm731.virgyferdian.my.id>** in **Chrome** or **Edge** (or open `index.html` from a download of this repo). Other browsers can't talk to USB devices.
3. Click **Connect mouse** and pick the Cooler Master device in the list.
4. Make your changes, then:
   - **Apply** tries them right away. They're gone when the mouse is switched off.
   - **Save to mouse** keeps them in the mouse's memory, so they work on any PC, even without this page.

The browser remembers the permission, so next time the page reconnects by itself.

## Supported setups

| Connection | Status |
|---|---|
| 2.4 GHz wireless dongle | Tested |
| USB cable | Tested |
| Bluetooth | Not tested yet |

The mouse keeps **separate settings for the cable and the wireless dongle**. To get the same setup in both, connect each way once and click **Save to mouse**.

## If something goes wrong

- **"The mouse didn't answer"**: the wireless mouse goes to sleep when idle. Move it, then click **Reload**. Also check that MasterPlus+ isn't running in the tray.
- **The Connect list is empty**: plug the dongle back in and refresh the page.
- **"This browser can't talk to USB devices"**: use Chrome or Edge.
- **Settings look wrong after a change**: switch the mouse off and on. Anything you applied without saving goes back to the last saved settings.

## Hosting it

The page is a single file (`index.html`) published with GitHub Pages. You can also open it straight from your disk or host it anywhere that serves HTTPS. WebHID needs a secure page (HTTPS or a local file).

## For developers

`mm731.py` is the command-line tool used to decode and test the protocol. `capdiff.py` and the `captures/` folder are the USB captures it was decoded from. See [DEVELOPMENT.md](DEVELOPMENT.md).

The protocol was worked out from USB captures of MasterPlus+ and from OpenRGB's code for related Cooler Master mice (`CMMMController`, `CMMM712Controller`).

## Disclaimer

This is an unofficial tool and isn't affiliated with or endorsed by Cooler Master. It only sends the same kinds of settings commands MasterPlus+ sends and never touches the firmware. Use it at your own risk.
