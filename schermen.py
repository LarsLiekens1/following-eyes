# schermen.py - maakt alle andere schermen zwart, met ogen die opduiken in het donker.
# Wordt automatisch gestart door ogen.py (alleen op Windows, alleen als je meerdere schermen hebt).
# Krijgt berichten van ogen.py via stdin, bijvoorbeeld:
#   zin IK ZIE JE      -> tekst tonen
#   staat weg          -> gezien / weg / dichtbij
#   glitch             -> korte storing
# Sluiten: Esc op een van de zwarte schermen, of ogen.py stoppen.

import sys, threading, queue, random, time, math, ctypes
from ctypes import wintypes
import tkinter as tk

user32 = ctypes.windll.user32


# --- Welke schermen zijn er? ---
class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def alle_schermen():
    """Geeft een lijst van (handle, links, boven, breedte, hoogte) voor elk scherm."""
    schermen = []
    Callback = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                  ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(h, dc, rect, data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(h, ctypes.byref(info))
        r = info.rcMonitor
        schermen.append((h, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    user32.EnumDisplayMonitors(None, None, Callback(cb), 0)
    return schermen


def mengen(kleur, sterkte):
    """Kleur (r, g, b) vermenigvuldigd met sterkte 0..1, als Tk-kleurcode."""
    r, g, b = (max(0, min(255, int(c * sterkte))) for c in kleur)
    return f"#{r:02x}{g:02x}{b:02x}"


# --- Een paar ogen dat in het donker opduikt ---
class Loerder:
    def __init__(self, w, h, kijk_richting, groot=False):
        schaal = min(w, h)
        self.r = schaal * (random.uniform(0.05, 0.09) if groot else random.uniform(0.015, 0.04))
        self.x = random.uniform(0.12, 0.88) * w
        self.y = random.uniform(0.15, 0.85) * h
        self.start = time.time()
        self.duur = random.uniform(3, 7)
        self.kijk = kijk_richting          # -1 of +1: kijken richting het hoofdscherm
        self.knipper = self.start + random.uniform(1, 3)

    def leeft(self, nu):
        return nu - self.start < self.duur

    def teken(self, c, nu):
        t = nu - self.start
        sterkte = min(1, t / 1.5) * min(1, (self.duur - t) / 1.0)    # langzaam in, langzaam uit
        sterkte *= 0.85 + 0.15 * math.sin(nu * 3 + self.x)           # gloed pulseert
        if self.knipper < nu < self.knipper + 0.15:
            return                                                    # ogen even dicht
        if nu > self.knipper + 0.15:
            self.knipper = nu + random.uniform(1.5, 4)
        for dx in (-1.6 * self.r, 1.6 * self.r):
            x, y, r = self.x + dx, self.y, self.r
            for i, f in enumerate((2.4, 1.8, 1.35)):                  # gloed: steeds kleinere ovalen
                rr = r * f
                c.create_oval(x - rr, y - rr * 0.55, x + rr, y + rr * 0.55, outline="",
                              fill=mengen((90, 0, 0), sterkte * (0.25 + 0.25 * i)))
            c.create_oval(x - r, y - r * 0.5, x + r, y + r * 0.5, outline="",
                          fill=mengen((255, 30, 10), sterkte))
            px = x + self.kijk * r * 0.35                             # spleetpupil kijkt opzij
            c.create_oval(px - r * 0.1, y - r * 0.45, px + r * 0.1, y + r * 0.45, outline="", fill="#000000")


class Scherm:
    def __init__(self, root, links, boven, w, h, hoofd_x):
        self.w, self.h = w, h
        self.kijk = 1 if hoofd_x > links + w / 2 else -1   # aan welke kant ligt het hoofdscherm?
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)                     # geen rand, geen titelbalk
        self.win.geometry(f"{w}x{h}+{links}+{boven}")
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.c = tk.Canvas(self.win, width=w, height=h, bg="black", highlightthickness=0, cursor="none")
        self.c.pack(fill="both", expand=True)
        self.loerders = []
        self.volgende = time.time() + random.uniform(2, 5)


class App:
    def __init__(self, terminal_hwnd):
        self.root = tk.Tk()
        self.root.withdraw()
        self.berichten = queue.Queue()
        self.staat = "weg"
        self.zin, self.zin_start = None, 0.0
        self.flits_tot = self.glitch_tot = 0.0

        alle = alle_schermen()
        hoofd = user32.MonitorFromWindow(terminal_hwnd, 2) if terminal_hwnd else None   # 2 = dichtstbijzijnde
        hoofd_rect = next((s for s in alle if s[0] == hoofd), alle[0])
        hoofd_x = hoofd_rect[1] + hoofd_rect[3] / 2
        self.schermen = [Scherm(self.root, l, b, w, h, hoofd_x) for (hm, l, b, w, h) in alle if hm != hoofd_rect[0]]
        if not self.schermen:
            sys.exit(0)                                     # maar één scherm: niets te doen
        for s in self.schermen:
            s.win.bind("<Escape>", lambda e: self.root.destroy())
        if terminal_hwnd:                                   # focus terug naar de terminal
            self.root.after(300, lambda: user32.SetForegroundWindow(terminal_hwnd))

        threading.Thread(target=self.lees, daemon=True).start()
        self.root.after(40, self.stap)

    def lees(self):
        """Leest berichten van ogen.py. Stopt ogen.py, dan stoppen wij ook."""
        for regel in sys.stdin:
            self.berichten.put(regel.strip())
        self.berichten.put("stop")

    def verwerk(self, nu):
        while not self.berichten.empty():
            bericht = self.berichten.get()
            soort, _, rest = bericht.partition(" ")
            if soort == "stop":
                self.root.destroy()
                return False
            if soort == "zin":
                self.zin, self.zin_start = rest, nu
            elif soort == "glitch":
                self.glitch_tot = nu + 0.3
            elif soort == "staat":
                if rest == "dichtbij" and self.staat != "dichtbij":
                    self.flits_tot = nu + 0.5                 # rode flits
                    for s in self.schermen:                   # grote ogen verschijnen meteen
                        s.loerders.append(Loerder(s.w, s.h, s.kijk, groot=True))
                self.staat = rest
        return True

    def stap(self):
        nu = time.time()
        if not self.verwerk(nu):
            return
        for s in self.schermen:
            c = s.c
            c.delete("all")
            flits = nu < self.flits_tot and random.random() < 0.7
            c.configure(bg="#3a0000" if flits else "black")

            # Nieuwe ogen laten opduiken: vaker als je weg bent, dan zijn ze overal
            if nu > s.volgende:
                aantal = random.randint(2, 5) if self.staat == "weg" else 1
                for _ in range(aantal):
                    s.loerders.append(Loerder(s.w, s.h, s.kijk))
                s.volgende = nu + (random.uniform(1.5, 4) if self.staat == "weg" else random.uniform(4, 9))
            s.loerders = [l for l in s.loerders if l.leeft(nu)]
            for l in s.loerders:
                l.teken(c, nu)

            # Tekst, hetzelfde als op het hoofdscherm
            if self.zin:
                t = nu - self.zin_start
                if t > 3.0:
                    self.zin = None
                elif random.random() > 0.08:                  # tekst hapert af en toe
                    sterkte = min(1, t / 0.3) * min(1, (3.0 - t) / 0.6)
                    grootte = -int(s.h * 0.09)                # negatief = in pixels
                    jx, jy = random.uniform(-3, 3), random.uniform(-3, 3)
                    c.create_text(s.w / 2 + jx, s.h * 0.5 + jy, text=self.zin, fill=mengen((190, 0, 8), sterkte),
                                  font=("Times New Roman", grootte, "bold"))

            # Storing: witte en grijze strepen
            if nu < self.glitch_tot:
                for _ in range(random.randint(3, 9)):
                    y = random.uniform(0, s.h)
                    grijs = random.randint(40, 200)
                    c.create_rectangle(0, y, s.w, y + random.uniform(2, s.h * 0.03), outline="",
                                       fill=f"#{grijs:02x}{grijs:02x}{grijs:02x}")
        self.root.after(40, self.stap)                        # ~25 beelden per seconde


def start(hwnd):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)        # echte pixels, ook bij 125%/150% schaal
    except Exception:
        pass
    try:
        App(hwnd).root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    start(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
