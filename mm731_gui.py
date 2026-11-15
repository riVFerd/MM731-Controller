"""MM731 desktop app: lighting, DPI, polling, lift-off and buttons in one window.

Run:  .venv\\Scripts\\pythonw.exe mm731_gui.py   (or double-click MM731.bat)
Apply = live, lost on power-off.  Save to mouse = also writes onboard flash.
"""
import tkinter as tk
from tkinter import colorchooser, ttk

import mm731 as m

MODES = ["static", "breathing", "cycle", "off"]
FUNCS = sorted(k for k in m.BTN_FUNCS if not k.startswith("key:")) + sorted(
    (k for k in m.BTN_FUNCS if k.startswith("key:")), key=lambda k: (len(k), k))
LOCKED = {"left", "combo-middle"}        # same guards as the CLI
NAMES = {v: k for k, v in m.BTN_FUNCS.items()}


def find_device():
    cands = [d for d in m.vendor_interfaces() if d.get("usage_page") == 0xFF0A]
    return min(cands, key=lambda d: d.get("interface_number", 0)) if cands else None


class Mouse:
    """One short HID session per action, so a sleeping mouse or replugged dongle can't wedge the app."""
    def __init__(self, info):
        self.info = info

    def __enter__(self):
        self.dev = m.Dev(self.info["path"], verbose=False)
        return m.Family712(self.dev)

    def __exit__(self, *_):
        self.dev.close()


def label_of(code):
    code = tuple(code)
    return NAMES.get(code) or (f"macro {code[1]}" if code[0] == 0xFF else f"code {bytes(code).hex(' ')}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MM731")
        self.resizable(False, False)
        self.info, self.per = None, {}
        self.status = tk.StringVar()
        pad = {"padx": 8, "pady": 4}

        # --- lighting
        lf = ttk.LabelFrame(self, text="Lighting")
        lf.grid(row=0, column=0, sticky="nsew", **pad)
        self.mode = tk.StringVar(value="static")
        cb = ttk.Combobox(lf, textvariable=self.mode, values=MODES, state="readonly", width=12)
        cb.grid(row=0, column=1, sticky="w", **pad)
        cb.bind("<<ComboboxSelected>>", lambda _: self.show_mode())
        ttk.Label(lf, text="Mode").grid(row=0, column=0, sticky="w", **pad)
        ttk.Label(lf, text="Colour").grid(row=1, column=0, sticky="w", **pad)
        self.rgb = (255, 0, 0)
        self.swatch = tk.Button(lf, width=10, relief="groove", command=self.pick_colour)
        self.swatch.grid(row=1, column=1, sticky="w", **pad)
        self.bright = tk.IntVar(value=255)
        self.speed = tk.IntVar(value=3)
        ttk.Label(lf, text="Brightness").grid(row=2, column=0, sticky="w", **pad)
        tk.Scale(lf, from_=0, to=255, orient="horizontal", variable=self.bright, length=160).grid(row=2, column=1, **pad)
        ttk.Label(lf, text="Speed").grid(row=3, column=0, sticky="w", **pad)
        tk.Scale(lf, from_=1, to=5, orient="horizontal", variable=self.speed, length=160).grid(row=3, column=1, **pad)

        # --- performance
        pf = ttk.LabelFrame(self, text="Performance")
        pf.grid(row=1, column=0, sticky="nsew", **pad)
        self.dpi = [tk.StringVar() for _ in range(m.DPI_STAGES)]
        self.active = tk.IntVar(value=1)
        ttk.Label(pf, text="Active").grid(row=0, column=2, **pad)
        for k in range(m.DPI_STAGES):
            ttk.Label(pf, text=f"DPI stage {k + 1}").grid(row=k + 1, column=0, sticky="w", padx=8)
            ttk.Spinbox(pf, from_=m.DPI_MIN, to=m.DPI_MAX, increment=m.DPI_STEP, textvariable=self.dpi[k],
                        width=8).grid(row=k + 1, column=1, padx=8, pady=1)
            ttk.Radiobutton(pf, variable=self.active, value=k + 1).grid(row=k + 1, column=2)
        self.poll = tk.StringVar(value="1000")
        self.lod = tk.StringVar(value="low")
        ttk.Label(pf, text="Polling (Hz)").grid(row=8, column=0, sticky="w", **pad)
        ttk.Combobox(pf, textvariable=self.poll, values=[str(h) for h in sorted(m.POLL_CODES)],
                     state="readonly", width=8).grid(row=8, column=1, **pad)
        ttk.Label(pf, text="Lift-off").grid(row=9, column=0, sticky="w", **pad)
        ttk.Combobox(pf, textvariable=self.lod, values=sorted(m.LOD_CODES), state="readonly",
                     width=8).grid(row=9, column=1, **pad)

        # --- buttons
        bf = ttk.LabelFrame(self, text="Buttons   (right column = hold middle + button)")
        bf.grid(row=0, column=1, rowspan=2, sticky="nsew", **pad)
        self.btn = {b: tk.StringVar() for b in m.BUTTONS}
        self.btn_boxes = {}
        for i, base in enumerate(m._BASE):
            ttk.Label(bf, text=base).grid(row=i, column=0, sticky="w", **pad)
            for col, name in ((1, base), (2, "combo-" + base)):
                box = ttk.Combobox(bf, textvariable=self.btn[name], values=FUNCS, width=14,
                                   state="disabled" if name in LOCKED else "readonly")
                box.grid(row=i, column=col, **pad)
                self.btn_boxes[name] = box

        # --- actions
        af = ttk.Frame(self)
        af.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Button(af, text="Reload", command=self.reload).pack(side="left")
        ttk.Button(af, text="Save to mouse", command=lambda: self.apply(save=True)).pack(side="right")
        ttk.Button(af, text="Apply", command=self.apply).pack(side="right", padx=8)
        ttk.Label(self, textvariable=self.status, foreground="#555").grid(row=3, column=0, columnspan=2,
                                                                          sticky="w", padx=8, pady=(0, 8))
        self.paint_swatch()
        self.after(50, self.reload)

    # --- helpers
    def paint_swatch(self):
        h = "#%02x%02x%02x" % self.rgb
        self.swatch.configure(bg=h, activebackground=h)

    def pick_colour(self):
        c = colorchooser.askcolor(color="#%02x%02x%02x" % self.rgb, parent=self)[0]
        if c:
            self.rgb = tuple(int(x) for x in c)
            self.paint_swatch()

    def show_mode(self):
        mi = MODES.index(self.mode.get())
        if mi in self.per:
            bright, spd, rgb = self.per[mi]
            self.bright.set(bright)
            self.speed.set(min(max(spd + 1, 1), 5))
            self.rgb = rgb
            self.paint_swatch()

    def fail(self, e):
        self.status.set(f"Error: {e}. Is MasterPlus+ closed and the mouse awake?")

    # --- device I/O
    def reload(self):
        self.info = find_device()
        if not self.info:
            self.status.set("Mouse not found. Plug in the dongle (or cable) and press Reload.")
            return
        try:
            with Mouse(self.info) as fam:
                mode, self.per = fam.read_lighting()
                p = fam.read_block()
                s = bytearray().join(fam.read_buttons())
        except OSError as e:
            return self.fail(e)
        self.mode.set(MODES[mode] if mode < len(MODES) else "static")
        self.show_mode()
        for k, (x, _) in enumerate(m.dpi_stages(p)):
            self.dpi[k].set(str(x))
        self.active.set(p[m.DPI_ACTIVE] + 1)
        self.poll.set(str({v: k for k, v in m.POLL_CODES.items()}.get(p[m.POLL], 1000)))
        self.lod.set({v: k for k, v in m.LOD_CODES.items()}.get(p[m.LOD], "low"))
        for i, b in enumerate(m.BUTTONS):
            label = label_of(s[1 + 2 * i:3 + 2 * i])
            self.btn[b].set(label)
            if label not in FUNCS:                      # keep unknown codes selectable as-is
                self.btn_boxes[b].configure(values=[label] + FUNCS)
        self.status.set(f"Loaded from mouse ({self.info.get('product_string')}).")

    def apply(self, save=False):
        if not self.info:
            return self.reload()
        try:
            dpis = []
            for k, v in enumerate(self.dpi, 1):
                x = int(v.get())
                if not (m.DPI_MIN <= x <= m.DPI_MAX and x % m.DPI_STEP == 0):
                    raise ValueError(f"DPI stage {k} must be {m.DPI_MIN}-{m.DPI_MAX} in steps of {m.DPI_STEP}")
                dpis.append(x)
        except ValueError as e:
            self.status.set(f"Error: {e}")
            return
        try:
            with Mouse(self.info) as fam:
                fam.set(self.mode.get(), *self.rgb, brightness=self.bright.get(), speed=self.speed.get())
                p = fam.read_block()
                old = bytes(p)
                for k, x in enumerate(dpis, 1):
                    m.set_dpi(p, k, x)
                p[m.DPI_ACTIVE] = self.active.get() - 1
                p[m.POLL] = m.POLL_CODES[int(self.poll.get())]
                p[m.LOD] = m.LOD_CODES[self.lod.get()]
                if bytes(p) != old:
                    fam.write_block(p)
                s = bytearray().join(fam.read_buttons())
                old = bytes(s)
                for i, b in enumerate(m.BUTTONS):
                    label = self.btn[b].get()
                    if label in m.BTN_FUNCS:
                        s[1 + 2 * i:3 + 2 * i] = bytes(m.BTN_FUNCS[label])
                if bytes(s) != old:
                    fam.write_buttons([s[:m.BLOCK_CHUNK], s[m.BLOCK_CHUNK:]])
                if save:
                    fam.save()
        except OSError as e:
            return self.fail(e)
        if self.mode.get() != "off":
            self.per[MODES.index(self.mode.get())] = (self.bright.get(), self.speed.get() - 1, self.rgb)
        self.status.set("Saved to mouse." if save else "Applied live (not saved: lost on power-off).")


if __name__ == "__main__":
    App().mainloop()
