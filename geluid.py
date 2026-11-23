# geluid.py - enge geluiden, live berekend met NumPy (geen audiobestanden nodig).
# Speelt af via winsound (zit standaard bij Python op Windows). Geen webcam/extra's nodig.
# Op niet-Windows of als er iets misgaat, blijft alles gewoon stil.

import io, wave, time, random
import numpy as np

try:
    import winsound                       # alleen op Windows
except ImportError:
    winsound = None

SR = 22050                                # samples per seconde


def _wav(signaal):
    """Zet een getallenrij (-1..1) om naar de bytes van een WAV-bestand, in het geheugen."""
    data = (np.clip(signaal, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data)
    return buf.getvalue()


def _t(duur):
    return np.linspace(0, duur, int(SR * duur), False)


def _laagdoor(x, k):
    """Simpele laagdoorlaatfilter (voortschrijdend gemiddelde): maakt ruis zachter/doffer."""
    return np.convolve(x, np.ones(k) / k, "same")


# --- De geluiden zelf ---
def _hartslag():
    """Lub-dub: twee lage bonken met een snelle uitdoving, zoals een hart."""
    def bonk(f0, duur, kracht):
        t = _t(duur)
        toonhoogte = f0 * (1 + 0.3 * np.exp(-t * 30))      # zakt snel in toonhoogte
        return np.sin(2 * np.pi * toonhoogte * t) * np.exp(-t * 17) * kracht
    return np.concatenate([bonk(62, 0.18, 0.95), np.zeros(int(SR * 0.11)),
                           bonk(50, 0.22, 0.75), np.zeros(int(SR * 0.05))])


def _gil():
    """Jumpscare: een stijgende, valse cluster van tonen met aanzwellende ruis."""
    duur = 1.1; t = _t(duur)
    toon = sum(np.sin(2 * np.pi * f * t * (1 + 1.8 * t / duur))
               for f in (210, 233, 277, 330, 466)) / 5
    ruis = np.random.uniform(-1, 1, t.size)
    env = np.minimum(1, t * 25) * np.exp(-np.maximum(t - 0.55, 0) * 4)
    return (0.6 * toon + 0.5 * ruis * (t / duur) ** 2) * env * 0.9


def _fluister():
    """Gefilterde ruis in ademhalingsvlagen, als iemand die vlak bij je oor fluistert."""
    duur = 1.5; t = _t(duur)
    ruis = _laagdoor(np.random.uniform(-1, 1, t.size), 25)
    adem = np.maximum(0, np.sin(2 * np.pi * 1.25 * t)) ** 2
    env = np.minimum(1, t * 7) * np.minimum(1, (duur - t) * 7)
    return ruis * adem * env * 0.55


def _brom():
    """Lage, onrustige bromtoon voor als er niemand is. Fade in/uit zodat herhalen niet klikt."""
    duur = 4.0; t = _t(duur)
    toon = (np.sin(2 * np.pi * 55 * t) + np.sin(2 * np.pi * 55.4 * t)
            + 0.6 * np.sin(2 * np.pi * 82.5 * t)) / 2.6
    golf = 0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t)
    env = np.minimum(1, t * 2) * np.minimum(1, (duur - t) * 2)
    return toon * golf * env * 0.4


class Geluid:
    """Beheert het afspelen. winsound speelt er maar één tegelijk, dus een jumpscare
    krijgt voorrang en onderbreekt de rest."""

    def __init__(self, aan=True):
        self.aan = bool(aan and winsound is not None)
        self._hoog_tot = 0.0          # tot wanneer een belangrijk geluid (gil) voorrang heeft
        self._laatste_hart = 0.0
        self._laatste_brom = 0.0
        self._ref = None              # houdt de bytes in leven tijdens het async afspelen
        self._clips = {}
        if self.aan:
            self._clips = {"hart": _wav(_hartslag()), "gil": _wav(_gil()),
                           "fluister": _wav(_fluister()), "brom": _wav(_brom())}

    def _speel(self, naam, prio=False):
        if not self.aan:
            return
        nu = time.time()
        if not prio and nu < self._hoog_tot:      # niet over een jumpscare heen spelen
            return
        self._ref = self._clips[naam]
        try:
            winsound.PlaySound(self._ref, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except RuntimeError:
            pass
        if prio:
            self._hoog_tot = nu + 1.0

    def gil(self):
        self._speel("gil", prio=True)

    def fluister(self):
        self._speel("fluister")

    def tick(self, nu, gezien, dichtbij):
        """Elke frame aanroepen. Regelt de hartslag (sneller bij dichtbij) en de bromtoon."""
        if not self.aan:
            return
        if gezien:
            interval = 0.62 if dichtbij else 0.95            # hartslag; dichtbij = sneller
            if nu - self._laatste_hart > interval:
                self._laatste_hart = nu
                self._speel("hart")
        elif nu - self._laatste_brom > 3.8 and nu > self._hoog_tot:
            self._laatste_brom = nu
            self._speel("brom")

    def stop(self):
        if self.aan:
            try:
                winsound.PlaySound(None, 0)
            except RuntimeError:
                pass


if __name__ == "__main__":        # klein testje: speelt de vier geluiden na elkaar
    g = Geluid()
    for naam in ("hart", "gil", "fluister", "brom"):
        print(naam)
        g._speel(naam, prio=True)
        time.sleep(1.6)
