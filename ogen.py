# ogen.py - twee enge ogen in de terminal die je via de webcam volgen
# Installeren: pip install -r requirements.txt
# Starten:     python ogen.py            (stoppen met Ctrl+C)
#              python ogen.py geel       (irisKleur: rood, geel, wit)
#
# Truc: elk teken is het halve blokje "▀". De bovenkant krijgt de voorgrondkleur,
# de onderkant de achtergrondkleur. Zo is elk teken 2 vierkante pixels.

import cv2                      # webcam + gezichtsherkenning
import numpy as np              # snel rekenen met grids
import shutil, time, random, sys, os, threading, math, subprocess
from collections import deque

MAP = os.path.dirname(os.path.abspath(__file__))
YUNET = os.path.join(MAP, "model", "face_detection_yunet_2023mar.onnx")

# --- Kleuren (RGB tussen 0 en 1) ---
def kl(*c):
    return np.array(c, np.float32)   # float32 rekent sneller dan het standaard float64

ACHTERGROND = kl(0.015, 0.0, 0.004)
HUID        = kl(0.52, 0.50, 0.46)    # bleek, lijkachtig
BLAUWPLEK   = kl(0.20, 0.08, 0.14)    # paarse kringen rond de ogen
WIMPER      = kl(0.03, 0.02, 0.02)
OOGWIT      = kl(0.86, 0.80, 0.64)    # vergeeld oogwit
ADER        = kl(0.70, 0.04, 0.04)    # bloedvaatjes
ROOD_RAND   = kl(0.75, 0.22, 0.18)    # rauwe, rode ooglidrand
BLOED       = kl(0.38, 0.0, 0.02)

IRIS_KLEUREN = {   # (bij de pupil, midden, buitenrand, pupil, gloed)
    "rood": ([1.0, 0.85, 0.30], [0.90, 0.12, 0.04], [0.30, 0.01, 0.01], [0.01, 0.0, 0.0], [1.0, 0.10, 0.04]),
    "geel": ([1.0, 0.95, 0.55], [0.92, 0.62, 0.05], [0.35, 0.16, 0.0], [0.01, 0.01, 0.0], [1.0, 0.65, 0.08]),
    "wit":  ([0.88, 0.90, 0.92], [0.72, 0.76, 0.80], [0.45, 0.50, 0.55], [0.55, 0.58, 0.62], [0.55, 0.75, 1.0]),
}


# Bloedvaatjes: lijntjes vanuit de ooghoeken met zijtakjes, per oog anders (vaste seed)
def maak_aders(seed):
    rnd = random.Random(seed)
    aders = []
    for hoek_s in (1.0, -1.0):                       # binnenhoek en buitenhoek
        for _ in range(5):
            phi = rnd.uniform(-0.55, 0.55)
            dx, dy = -hoek_s * math.cos(phi), math.sin(phi) * 0.5
            L = rnd.uniform(0.35, 0.62)
            ox, oy = hoek_s * 0.97, 0.05 * hoek_s
            aders.append((ox, oy, dx, dy, L, rnd.uniform(0, 6), 1.0))
            phi2 = phi + rnd.choice([-0.6, 0.6])      # zijtakje vanaf 40% van de ader
            aders.append((ox + dx * L * 0.4, oy + dy * L * 0.4, -hoek_s * math.cos(phi2),
                          math.sin(phi2) * 0.5, L * 0.5, rnd.uniform(0, 6), 0.7))
    return aders

ADERS = {-1: maak_aders(7), 1: maak_aders(13)}


# --- Kleine hulpfuncties ---
def ss(e0, e1, x):
    """smoothstep: zachte overgang van 0 (bij e0) naar 1 (bij e1). Geeft gladde randen."""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    """Meng kleur a met kleur b. t=0 -> a, t=1 -> b."""
    return a + (b - a) * t[..., None]


# --- Eén oog tekenen ---
def teken_oog(img, cx, cy, a, kant, st):
    """Tekent een oog met middelpunt (cx, cy) en halve breedte a (in pixels).
    kant = -1 voor het linkeroog op het scherm, +1 voor het rechteroog."""
    H, W = img.shape[:2]
    x0, x1 = max(int(cx - 2.0 * a), 0), min(int(cx + 2.0 * a) + 1, W)
    y0, y1 = max(int(cy - 1.45 * a), 0), min(int(cy + 1.6 * a) + 1, H)
    if x1 <= x0 or y1 <= y0:
        return
    X, Y = np.meshgrid(np.arange(x0, x1, dtype=np.float32) + 0.5, np.arange(y0, y1, dtype=np.float32) + 0.5)
    s = (X - cx) / a * -kant      # -1..1 over het oog, +1 = binnenhoek (bij de neus)
    v = (Y - cy) / a              # verticaal, negatief = omhoog
    stuk = img[y0:y1, x0:x1]
    gx = st["kijk_x"] + st["los"][kant][0]       # "los": een oog dat even zijn eigen kant op rolt
    gy = st["kijk_y"] + st["los"][kant][1]
    binnen_kl, midden_kl, buiten_kl, pupil_kl, gloed_kl = (kl(*c) for c in IRIS_KLEUREN[st["kleur"]])

    # Vorm van de oogleden (amandelvorm)
    w = np.clip(1 - s * s, 0, 1) ** 0.7
    tilt = 0.05 * s
    boven = -0.40 * w * (1 + 0.12 * s) + tilt + 0.08 * gy
    onder = 0.27 * w * (1 - 0.15 * s) + tilt

    # 1. Bleke huid met diep ingevallen, donkere oogkassen
    rr = np.sqrt((s / 2.0) ** 2 + ((v + 0.15) / 1.25) ** 2)
    m_huid = 1 - ss(0.45, 1.0, rr)
    licht = 1.0 - 0.25 * (v + 0.3)
    kas = 1 - 0.65 * np.exp(-((v + 0.05) / 0.55) ** 2 - (s / 1.2) ** 2)
    huid = HUID * (licht * kas)[..., None]
    kring = np.exp(-((v - (onder + 0.20)) / 0.14) ** 2) * ss(1.3, 0.3, np.abs(s))      # wallen
    kring = np.maximum(kring, 0.7 * np.exp(-((v - (boven - 0.18)) / 0.16) ** 2) * ss(1.3, 0.3, np.abs(s)))
    huid = mix(huid, BLAUWPLEK, 0.75 * kring)
    plooi_v = boven - 0.12 * np.sqrt(w) - 0.02
    plooi = np.exp(-(((v - plooi_v) * a) / max(0.8, 0.03 * a)) ** 2) * ss(1.1, 0.9, np.abs(s))
    huid = huid * (1 - 0.5 * plooi)[..., None]
    stuk = mix(stuk, huid, m_huid)

    # 2. Bloedtraan uit de ooghoek, groeit langzaam
    lengte = st["traan"][0 if kant < 0 else 1]
    if lengte > 0.02:
        s_t = 0.55 if kant < 0 else -0.65                                  # verschillende plek per oog
        v_t = 0.27 * (1 - s_t * s_t) ** 0.7 * (1 - 0.15 * s_t) + 0.05 * s_t
        x_t = cx + s_t * a * -kant
        xc = x_t + 0.04 * a * np.sin((v - v_t) * 7)                        # beetje kronkelen
        dikte = max(0.7, 0.035 * a) * (1 - 0.35 * np.clip((v - v_t) / lengte, 0, 1))
        m_t = ss(dikte + 0.5, dikte - 0.5, np.abs(X - xc)) * ss(v_t - 0.02, v_t + 0.03, v) * ss(v_t + lengte, v_t + lengte - 0.02, v)
        druppel = ss(1.8 * dikte + 0.5, 1.8 * dikte - 0.5, np.hypot(X - xc, (v - v_t - lengte) * a))
        stuk = mix(stuk, BLOED, 0.92 * np.maximum(m_t, druppel))

    # 3. Openheid: bij knipperen schuift het bovenste ooglid naar het onderste
    o = st["open"]
    onder_e = onder - (1 - min(o, 1)) * 0.04
    boven_e = onder_e + (boven - onder_e) * o
    d_boven = (v - boven_e) * a          # afstand tot bovenste ooglid in pixels (+ = binnen)
    d_onder = (onder_e - v) * a
    m_oog = ss(-0.2, 0.8, np.minimum(d_boven, d_onder)) * ss(1.0, 0.96, np.abs(s))

    # 4. Vergeeld oogwit vol bloedvaatjes, rood naar de randen
    oog = OOGWIT * (1 - 0.35 * s * s)[..., None]
    aders = np.zeros_like(s)
    for ox, oy, dx, dy, L, fase, sterk in ADERS[kant]:
        ls, lv = s - ox, v - oy
        langs = ls * dx + lv * dy                                   # afstand langs de ader
        dwars = -ls * dy + lv * dx + 0.025 * np.sin(langs * 18 + fase)  # afstand ernaast, kronkelend
        dik = max(0.35, 0.02 * a) * sterk * (1 - np.clip(langs / L, 0, 1))
        m = ss(dik + 0.5, dik - 0.5, np.abs(dwars) * a) * ss(-0.02, 0.02, langs) * ss(L, 0.7 * L, langs)
        aders = np.maximum(aders, m)
    r0 = np.hypot(s, v * 2.2)
    oog = mix(oog, ROOD_RAND, 0.45 * ss(0.45, 1.0, r0))
    oog = mix(oog, ADER, aders * 0.9)

    # 5. Gloeiende iris met een spleetpupil (zoals een kat of reptiel)
    ri = 0.40 * a
    ix = cx + gx * 0.45 * a
    iy = cy + gy * 0.16 * a + 0.01 * a
    dx, dy = X - ix, Y - iy
    rho = np.sqrt(dx * dx + dy * dy)
    hoekr = np.arctan2(dy, dx)
    rn = rho / ri
    gloei = st["gloei"]
    vezel = (0.6 * (0.5 + 0.5 * np.sin(hoekr * 41 + 2.5 * np.sin(hoekr * 9 + rn * 3) + rn * 5))
             + 0.4 * (0.5 + 0.5 * np.sin(hoekr * 17 - rn * 8 + 1.3)))
    iris = mix(np.broadcast_to(binnen_kl, rn.shape + (3,)), midden_kl, ss(0.15, 0.55, rn))
    iris = mix(iris, buiten_kl, ss(0.6, 1.0, rn))
    iris = iris * ((0.6 + 0.6 * vezel) * (0.75 + 0.3 * gloei))[..., None]
    iris = iris * (1 - 0.8 * ss(0.82, 1.0, rn))[..., None]                       # zwarte buitenring
    oog = oog + gloed_kl * (0.35 * gloei * np.exp(-np.maximum(rho - ri, 0) / (0.25 * ri)))[..., None]
    oog = mix(oog, iris, ss(ri + 0.6, ri - 0.6, rho))
    rx = max(0.6, ri * st["spleet"])                                              # breedte van de spleet
    ry = ri * 0.92
    d_pup = (np.sqrt((dx / rx) ** 2 + (dy / ry) ** 2) - 1) * rx
    oog = mix(oog, pupil_kl, ss(0.6, -0.6, d_pup))

    # 6. Schaduw van het bovenste ooglid en een klein, dof lichtpuntje
    schaduw = (1 - 0.55 * np.exp(-np.maximum(d_boven, 0) / (0.10 * a + 0.8))) \
            * (1 - 0.2 * np.exp(-np.maximum(d_onder, 0) / (0.06 * a + 0.6)))
    oog = oog * schaduw[..., None]
    hr = max(0.7, 0.10 * ri)
    d1 = np.hypot(X - (ix - 0.35 * ri), Y - (iy - 0.38 * ri))
    oog = mix(oog, kl(1.0, 0.95, 0.9), ss(hr + 0.6, hr - 0.6, d1) * 0.5)

    stuk = mix(stuk, oog, m_oog)

    # 7. Gloed die over de oogleden valt
    stuk = stuk + gloed_kl * (0.10 * gloei * np.exp(-np.maximum(rho - ri, 0) / (0.6 * ri)) * m_huid)[..., None]

    # 8. Rauwe rode rand onder het oog, wimpers boven
    binnen_oog = ss(1.05, 0.9, np.abs(s))
    stuk = mix(stuk, ROOD_RAND, 0.7 * np.exp(-((d_onder + 0.7) / 0.9) ** 2) * binnen_oog)
    lt = max(0.9, 0.045 * a) * (1 + 0.6 * np.clip(-s, 0, 1))
    stuk = mix(stuk, WIMPER, 0.92 * np.exp(-((d_boven + 0.3) / lt) ** 2) * binnen_oog)

    img[y0:y1, x0:x1] = stuk * st["licht"]       # flikkerend licht


# --- Instellingen voor het volgen ---
VASTHOUDEN = 2.5    # seconden dat de ogen blijven kijken waar je het laatst was
VERSTERKING = 1.6   # hoe ver de ogen draaien: hoger = sneller naar de rand
DICHTBIJ = 0.32     # gezicht breder dan dit deel van het beeld = "te dichtbij"
ANDERE_SCHERMEN = True   # meerdere schermen? dan worden de andere zwart, met ogen in het donker

A_MAX = 34   # grootste oog (halve breedte in pixels) dat we op volle resolutie tekenen

def teken_frame(Wp, Hp, st):
    """Tekent een volledig beeld van Wp x Hp pixels. Geeft uint8 RGB terug."""
    a = min(Wp / 7.2, Hp * 0.40)                  # halve breedte van een oog
    schaal = min(1.0, A_MAX / a)                  # heel groot scherm? kleiner tekenen en opschalen
    w, h = max(1, round(Wp * schaal)), max(1, round(Hp * schaal))
    img = np.empty((h, w, 3), np.float32)
    img[:] = ACHTERGROND
    a *= schaal
    for kant in (-1, 1):
        teken_oog(img, w / 2 + kant * 1.9 * a, h * 0.48, a, kant, st)
    img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    if schaal < 1:
        img = cv2.resize(img, (Wp, Hp), interpolation=cv2.INTER_LINEAR)
    return img


# --- Enge extra's: tekst in beeld en glitches ---
ZINNEN = {
    "terug":    ["DAAR BEN JE", "IK HEB JE GEMIST", "WAAR WAS JE?"],
    "weg":      ["KOM TERUG", "IK WEET WAAR JE BENT", "JE KUNT NIET VLUCHTEN"],
    "dichtbij": ["TE DICHTBIJ", "DICHTER...", "IK RUIK JE"],
    "staren":   ["IK ZIE JE", "KIJK NIET WEG", "ACHTER JE", "WIE STAAT ER NAAST JE?", "KNIPPER NIET"],
    "wachten":  ["IK WACHT", "IK BEN NOG HIER", "LAAT ME ERUIT"],
}


def tekst_op_beeld(img, tekst, sterkte):
    """Zet grote, rode, trillende tekst onderaan het beeld (onder de ogen)."""
    H, W = img.shape[:2]
    font = cv2.FONT_HERSHEY_TRIPLEX
    (tw, th), _ = cv2.getTextSize(tekst, font, 1.0, 1)
    schaal = min(W * 0.7 / tw, H * 0.09 / th)
    dikte = max(1, round(schaal * 1.2))
    (tw, th), _ = cv2.getTextSize(tekst, font, schaal, dikte)
    x = int((W - tw) / 2 + random.uniform(-1, 1) * W * 0.004)
    y = int(H * 0.965 + random.uniform(-1, 1) * H * 0.004)
    laag = np.zeros(img.shape[:2], np.uint8)
    cv2.putText(laag, tekst, (x, y), font, schaal, 255, dikte, cv2.LINE_AA)
    m = (laag.astype(np.float32) / 255 * sterkte)[..., None]
    img[:] = (img * (1 - m) + np.array([175, 0, 5], np.float32) * m).astype(np.uint8)


def glitch(img, kracht):
    """Verschuift stroken van het beeld en trekt de kleuren uit elkaar, zoals een kapotte tv."""
    H, W = img.shape[:2]
    for _ in range(int(2 + kracht * 8)):
        y0 = random.randrange(H)
        y1 = min(H, y0 + random.randint(1, max(2, H // 8)))
        img[y0:y1] = np.roll(img[y0:y1], int(random.uniform(-1, 1) * W * 0.08 * kracht), axis=1)
    verschuif = int(W * 0.012 * kracht) + 1
    img[..., 0] = np.roll(img[..., 0], verschuif, axis=1)      # rood naar rechts
    img[..., 2] = np.roll(img[..., 2], -verschuif, axis=1)     # blauw naar links
    if random.random() < 0.15 * kracht:
        img[:] = 255 - img                                     # heel even negatief beeld


# --- Beeld omzetten naar tekst met kleurcodes ---
_fg, _bg = {}, {}

def fg(k):
    c = _fg.get(k)
    if c is None:
        c = _fg[k] = f"\x1b[38;2;{k >> 16};{(k >> 8) & 255};{k & 255}m"
    return c

def bg(k):
    c = _bg.get(k)
    if c is None:
        c = _bg[k] = f"\x1b[48;2;{k >> 16};{(k >> 8) & 255};{k & 255}m"
    return c


def naar_ansi(img, vorige):
    """Zet het beeld om naar terminaltekst. Alleen het stuk van elke rij dat veranderd is
    wordt opnieuw geschreven: dat scheelt veel en voorkomt geflikker."""
    pak = lambda p: (p[..., 0].astype(np.int32) << 16) | (p[..., 1].astype(np.int32) << 8) | p[..., 2]
    kt, kb = pak(img[0::2]), pak(img[1::2])      # bovenste en onderste pixel van elk teken
    if vorige is None or vorige[0].shape != kt.shape:
        anders = np.ones(kt.shape, bool)
    else:
        anders = (kt != vorige[0]) | (kb != vorige[1])
    uit = []
    for r in np.nonzero(anders.any(axis=1))[0]:
        kolommen = np.nonzero(anders[r])[0]
        c0, c1 = kolommen[0], kolommen[-1] + 1     # alleen van eerste tot laatste verandering
        uit.append(f"\x1b[{r + 1};{c0 + 1}H")
        cf = cb = -1
        for t, b in zip(kt[r, c0:c1].tolist(), kb[r, c0:c1].tolist()):
            if t == b:                            # beide helften dezelfde kleur: spatie volstaat
                if b != cb:
                    uit.append(bg(b)); cb = b
                uit.append(" ")
            else:
                if t != cf:
                    uit.append(fg(t)); cf = t
                if b != cb:
                    uit.append(bg(b)); cb = b
                uit.append("▀")
    uit.append("\x1b[0m")
    if len(_fg) > 60000:
        _fg.clear(); _bg.clear()
    return "".join(uit), (kt, kb)


# --- Webcam in een aparte thread, zodat het tekenen nooit op de camera moet wachten ---
# --- De andere schermen (schermen.py draait als apart programma) ---
class AndereSchermen:
    def __init__(self, terminal_hwnd):
        self.proces = None
        if not (ANDERE_SCHERMEN and os.name == "nt"):
            return
        try:
            self.proces = subprocess.Popen(
                [sys.executable, os.path.join(MAP, "schermen.py"), str(terminal_hwnd)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            self.proces = None

    def zend(self, bericht):
        """Stuurt een bericht naar schermen.py, bv. "zin IK ZIE JE" of "staat weg"."""
        if self.proces and self.proces.poll() is None:
            try:
                self.proces.stdin.write(bericht + "\n")
                self.proces.stdin.flush()
            except OSError:
                self.proces = None

    def stop(self):
        if self.proces:
            try:
                self.proces.stdin.close()                # schermen.py ziet "einde" en sluit
                self.proces.wait(timeout=2)
            except Exception:
                self.proces.kill()


class Camera(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.cam = self.open_camera()
        # YuNet: klein neuraal netwerk, veel betrouwbaarder dan de oude Haar cascade
        self.yunet = None
        if os.path.exists(YUNET) and hasattr(cv2, "FaceDetectorYN"):
            self.yunet = cv2.FaceDetectorYN.create(YUNET, "", (416, 234), 0.5, 0.3, 5000)
        else:
            self.haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.gezicht = None      # (x, y, grootte, tijdstip) van het laatst gevonden gezicht
        self.helderheid = 128
        self.frame_tijden = deque(maxlen=30)   # om de fps van de camera te meten
        self.treffers = deque(maxlen=30)       # gezicht gevonden ja/nee, per frame
        self.actief = True

    @staticmethod
    def open_camera():
        """Probeert de webcam op verschillende manieren te openen en kijkt of er echt
        beelden uit komen. Geeft None terug als dat niet lukt."""
        cv2.setLogLevel(0) if hasattr(cv2, "setLogLevel") else None   # geen spam van waarschuwingen
        pogingen = [cv2.CAP_DSHOW, cv2.CAP_MSMF] if os.name == "nt" else [cv2.CAP_ANY]
        for index in (0, 1):
            for api in pogingen:
                cam = cv2.VideoCapture(index, api)
                if not cam.isOpened():
                    continue
                # MJPG: veel webcams geven anders maar een paar beelden per seconde
                cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)        # breedbeeld = meer zicht opzij
                cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)            # altijd het nieuwste beeld
                t, goed = time.time(), 0
                while time.time() - t < 2.5 and goed < 5:      # komen er echt beelden uit?
                    ok, _ = cam.read()
                    goed += ok
                if goed >= 5:
                    return cam
                cam.release()
        return None

    def zoek(self, klein):
        """Geeft (x, y, w, h) van het grootste gezicht terug, of None."""
        if self.yunet is not None:
            self.yunet.setInputSize((klein.shape[1], klein.shape[0]))
            _, gez = self.yunet.detect(klein)
            if gez is None or len(gez) == 0:
                return None
            return max((g[:4] for g in gez), key=lambda f: f[2] * f[3])
        grijs = cv2.equalizeHist(cv2.cvtColor(klein, cv2.COLOR_BGR2GRAY))
        gez = self.haar.detectMultiScale(grijs, 1.1, 5, minSize=(30, 30))
        return max(gez, key=lambda f: f[2] * f[3]) if len(gez) else None

    def run(self):
        while self.actief:
            ok, frame = self.cam.read()
            if not ok:
                time.sleep(0.05)
                continue
            self.frame_tijden.append(time.time())
            klein = cv2.resize(frame, (416, int(416 * frame.shape[0] / frame.shape[1])))
            self.helderheid = float(klein.mean())
            if self.helderheid < 90:                     # donker beeld? eerst wat lichter maken
                klein = cv2.convertScaleAbs(klein, alpha=min(3.0, 100 / max(self.helderheid, 1)))
            g = self.zoek(klein)
            self.treffers.append(g is not None)
            if g is not None:
                x, y, w, h = g
                bh, bw = klein.shape[:2]
                fx = 1 - (x + w / 2) / bw * 2    # gespiegeld, anders kijken de ogen de verkeerde kant op
                fy = (y + h / 2) / bh * 2 - 1
                self.gezicht = (fx, fy, w / bw, time.time())

    def fps(self):
        t = self.frame_tijden
        return (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 and t[-1] > t[0] else 0.0


def ctypes_hwnd():
    import ctypes
    return ctypes.windll.user32.GetForegroundWindow() or 0


def main():
    kleur = sys.argv[1] if len(sys.argv) > 1 else "rood"
    if kleur not in IRIS_KLEUREN:
        sys.exit(f"Onbekende kleur '{kleur}'. Kies uit: {', '.join(IRIS_KLEUREN)}")
    if not hasattr(cv2, "CascadeClassifier"):
        sys.exit("Je gebruikt OpenCV 5. Activeer eerst de .venv of doe: pip install \"opencv-python<5\"")

    # Het venster dat nu vooraan staat is de terminal: zo weten we op welk scherm de ogen staan
    terminal_hwnd = ctypes_hwnd() if os.name == "nt" else 0
    cam = Camera()
    if cam.cam is None:
        sys.exit("De webcam geeft geen beeld.\n"
                 "- Draait ogen.py misschien nog in een ander venster? Sluit dat eerst.\n"
                 "- Gebruikt een ander programma de camera (Discord, Teams, Camera-app)?\n"
                 "- Windows Instellingen > Privacy > Camera: staat toegang voor apps aan?")
    cam.start()
    schermen = AndereSchermen(terminal_hwnd)

    os.system("")                                   # ANSI-codes aanzetten op Windows
    out = sys.stdout.buffer
    out.write(b"\x1b[?1049h\x1b[?25l\x1b[2J")       # apart scherm, cursor verbergen

    st = {"kijk_x": 0.0, "kijk_y": 0.0, "open": 1.0, "spleet": 0.15, "gloei": 1.0,
          "licht": 1.0, "traan": [0.0, 0.0], "kleur": kleur, "los": {-1: [0.0, 0.0], 1: [0.0, 0.0]}}
    doel_x = doel_y = 0.0
    basis_open = 0.6
    knipper_start, volgende_knipper = -1.0, time.time() + random.uniform(4, 8)
    trek_tot = 0.0                     # oogleden trillen tot dit tijdstip
    flikker_tot, volgende_flikker = 0.0, time.time() + random.uniform(3, 8)
    zoek_doel = (0.0, 0.0); volgende_blik = 0.0
    vorige, grootte = None, None
    start = laatst = time.time()
    zin, zin_start, zin_duur = None, 0.0, 0.0          # enge tekst die nu in beeld staat
    volgende_zin = start + random.uniform(10, 20)
    glitch_tot, volgende_glitch = 0.0, start + random.uniform(8, 15)
    los_kant, los_tot, volgende_los = -1, 0.0, start + random.uniform(15, 30)
    los_doel = (0.0, 0.0)
    was_gezien = was_dichtbij = False
    weg_sinds = start

    def zeg(soort, duur=2.5):
        nonlocal zin, zin_start, zin_duur
        zin, zin_start, zin_duur = random.choice(ZINNEN[soort]), time.time(), duur
        schermen.zend("zin " + zin)

    try:
        while True:
            nu = time.time()
            dt = min(nu - laatst, 0.1)
            laatst = nu
            glad = lambda snelheid: 1 - math.exp(-dt * snelheid)   # vloeiend bewegen, los van de fps

            # --- Waar kijken we naar? ---
            g = cam.gezicht
            weg = nu - g[3] if g else 999                    # hoe lang geen gezicht gezien
            gezien = weg < VASTHOUDEN                        # even kwijt? laatste positie vasthouden
            dichtbij = weg < 1.0 and g[2] > DICHTBIJ
            if gezien:
                rx = max(-1, min(1, g[0] * VERSTERKING))
                ry = max(-1, min(1, g[1] * VERSTERKING))
                if weg > 0.3 and abs(g[0]) > 0.5:            # aan de zijkant uit beeld gelopen?
                    rx = math.copysign(1.0, g[0])            # dan helemaal die kant op blijven kijken
                rx += random.uniform(-0.015, 0.015)          # trillende, starende blik
                snel = 30
            else:                                            # niemand: schichtig rondzoeken
                if nu > volgende_blik:
                    hoek = random.uniform(0, 2 * math.pi)
                    zoek_doel = (math.cos(hoek) * 0.85, math.sin(hoek) * 0.6)
                    volgende_blik = nu + random.uniform(0.5, 1.6)
                rx, ry = zoek_doel
                snel = 18
            doel_x += (rx - doel_x) * glad(snel)
            doel_y += (ry - doel_y) * glad(snel)
            st["kijk_x"] += (doel_x - st["kijk_x"]) * glad(snel)
            st["kijk_y"] += (doel_y - st["kijk_y"]) * glad(snel)
            lengte = math.hypot(st["kijk_x"], st["kijk_y"])
            if lengte > 1:
                st["kijk_x"] /= lengte; st["kijk_y"] /= lengte

            # --- Stemming ---
            # niemand: half dicht en loerend / gezien: wijd open staren / dichtbij: helemaal open
            doel_open = 1.2 if dichtbij else (1.08 if gezien else 0.6)
            basis_open += (doel_open - basis_open) * glad(6 if gezien else 2)
            # spleetpupil: dun in het licht, wordt groot en rond als je dichtbij komt
            doel_spleet = 0.85 if dichtbij else 0.10 + 0.20 * (1 - cam.helderheid / 255)
            st["spleet"] += (doel_spleet - st["spleet"]) * glad(4 if dichtbij else 2)
            doel_gloei = 1.6 if dichtbij else (1.0 if gezien else 0.6)
            st["gloei"] += (doel_gloei - st["gloei"]) * glad(3)
            st["gloei_nu"] = st["gloei"] + 0.15 * math.sin(nu * 2.2)

            # Bloedtranen groeien langzaam (sneller als je dichtbij bent)
            groei = dt * (0.03 if dichtbij else 0.012)
            if nu - start > 4:
                st["traan"][0] = min(0.95, st["traan"][0] + groei)
            if nu - start > 11:
                st["traan"][1] = min(0.8, st["traan"][1] + groei)

            # --- Knipperen (zelden: ze staren) en trillende oogleden ---
            if nu > volgende_knipper:
                knipper_start = nu
                volgende_knipper = nu + random.uniform(5, 12)
            p = (nu - knipper_start) / 0.18
            dicht = ss(0, 0.4, p) if p < 0.4 else (1 - ss(0.4, 1, p) if p < 1 else 0.0)
            if gezien and random.random() < dt * 0.25:
                trek_tot = nu + random.uniform(0.2, 0.5)
            trek = 0.10 * abs(math.sin(nu * 55)) if nu < trek_tot else 0.0
            st["open"] = max(0.0, basis_open * (1 - float(dicht)) - trek)

            # --- Flikkerend licht, zoals een kapotte lamp ---
            if nu > volgende_flikker:
                flikker_tot = nu + random.uniform(0.1, 0.5)
                volgende_flikker = nu + random.uniform(0.8, 2.5) if dichtbij else nu + random.uniform(3, 9)
            st["licht"] = random.choice([0.15, 0.4, 1.0]) if nu < flikker_tot else 1.0

            # --- Gebeurtenissen: tekst, glitches en een oog dat wegrolt ---
            if gezien and not was_gezien:
                if nu - weg_sinds > 4:
                    zeg("terug")
                    glitch_tot = nu + 0.25
            elif was_gezien and not gezien:
                zeg("weg", 3.0)
                weg_sinds = nu
            if dichtbij and not was_dichtbij:                # jumpscare
                zeg("dichtbij", 2.0)
                glitch_tot = nu + 0.7
                flikker_tot = nu + 0.6
            if (gezien, dichtbij) != (was_gezien, was_dichtbij):
                schermen.zend("staat " + ("dichtbij" if dichtbij else "gezien" if gezien else "weg"))
            was_gezien, was_dichtbij = gezien, dichtbij
            if nu > volgende_zin:
                if zin is None or nu - zin_start > zin_duur:
                    zeg("staren" if gezien else "wachten", 3.0)
                volgende_zin = nu + random.uniform(12, 25)
            if nu > volgende_glitch:
                glitch_tot = nu + random.uniform(0.08, 0.25)
                schermen.zend("glitch")
                volgende_glitch = nu + (random.uniform(1.5, 4) if dichtbij else random.uniform(6, 15))
            if nu > volgende_los and gezien:
                los_kant, los_tot = random.choice([-1, 1]), nu + random.uniform(1.0, 2.0)
                hoek = random.uniform(0, 2 * math.pi)
                los_doel = (math.cos(hoek) * 0.9, math.sin(hoek) * 0.5)
                volgende_los = nu + random.uniform(15, 30)
            for kant in (-1, 1):
                doel = los_doel if (kant == los_kant and nu < los_tot) else (0.0, 0.0)
                for i in (0, 1):
                    st["los"][kant][i] += (doel[i] - st["los"][kant][i]) * glad(10)

            # --- Tekenen ---
            cols, rows = shutil.get_terminal_size()
            rows -= 1                                         # laatste regel voor de status
            if (cols, rows) != grootte:                       # venster veranderd: alles opnieuw
                grootte, vorige = (cols, rows), None
                out.write(b"\x1b[0m\x1b[2J")
            if cols < 20 or rows < 6:
                out.write(b"\x1b[HMaak het venster groter")
                out.flush(); time.sleep(0.2); continue

            gloei_basis = st["gloei"]
            st["gloei"] = st["gloei_nu"]
            img = teken_frame(cols, rows * 2, st)
            st["gloei"] = gloei_basis
            if zin is not None:
                leeftijd = nu - zin_start
                if leeftijd > zin_duur:
                    zin = None
                else:
                    sterkte = float(ss(0, 0.3, leeftijd) * (1 - ss(zin_duur - 0.6, zin_duur, leeftijd)))
                    if random.random() < 0.08:
                        sterkte *= 0.2                        # tekst hapert af en toe
                    tekst_op_beeld(img, zin, sterkte)
            if nu < glitch_tot:
                glitch(img, 1.0 if dichtbij else 0.5)
            tekst, vorige = naar_ansi(img, vorige)

            # Statusregel: handig om te zien of het aan de camera of aan de detectie ligt
            treffers = sum(cam.treffers) / len(cam.treffers) * 100 if cam.treffers else 0
            kl = "\x1b[38;2;200;40;40m" if gezien else "\x1b[38;2;90;70;70m"
            status = (f"{kl}{'● gezicht' if gezien else '○ zoeken...'}\x1b[38;2;90;70;70m"
                      f"   camera {cam.fps():4.1f} fps   herkend {treffers:3.0f}%"
                      f"   {'YuNet' if cam.yunet is not None else 'Haar'}")
            tekst += f"\x1b[{rows + 1};1H\x1b[0m\x1b[2K{status}\x1b[0m"
            # \x1b[?2026h/l = "synchronized update": terminal toont het frame pas als het compleet is
            out.write(("\x1b[?2026h" + tekst + "\x1b[?2026l").encode("utf-8"))
            out.flush()

            rust = 1 / 30 - (time.time() - nu)                # ~30 frames per seconde
            if rust > 0:
                time.sleep(rust)

    except KeyboardInterrupt:
        pass                                                  # Ctrl+C = netjes stoppen
    finally:
        cam.actief = False
        schermen.stop()
        time.sleep(0.1)
        cam.cam.release()
        out.write(b"\x1b[0m\x1b[?25h\x1b[?1049l")            # cursor en gewone scherm terug
        out.flush()


if __name__ == "__main__":
    main()
