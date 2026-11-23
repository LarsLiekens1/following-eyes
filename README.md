# 👁️ Following Eyes

Twee enge, gloeiende ogen in je terminal die je via de webcam volgen.
Bloeddoorlopen, met spleetpupillen en bloedtranen. Kom je te dichtbij, dan gaan ze wijd open en begint het licht te flikkeren.

Alles wordt live berekend met NumPy en getekend met kleur-tekens (`▀`) in de terminal. Er worden geen afbeeldingen ingeladen.

## Installeren

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Starten

Dubbelklik op **`start.bat`**: dat opent Windows Terminal op volledig scherm.

Of in de terminal:

```
python ogen.py          # rode ogen
python ogen.py geel     # of: rood, geel, wit
```

Stoppen met `Ctrl+C`. Meer detail: zoom uit met `Ctrl` + `-`.

## Hoe het werkt

1. **Webcam:** OpenCV leest de camera in een aparte thread.
2. **Gezicht zoeken:** [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), een klein neuraal netwerk, vindt je gezicht (map `model/`).
3. **Kijkrichting:** het midden van je gezicht wordt een getal tussen -1 en 1.
4. **Tekenen:** voor elke pixel worden huid, oogleden, oogwit, iris en pupil berekend met wiskunde.
5. **Terminal:** elk teken `▀` is 2 pixels (voorgrond- en achtergrondkleur). Alleen wat verandert wordt opnieuw geschreven.

## Instellingen

Bovenaan `ogen.py`:

| Instelling    | Betekenis                                          |
|---------------|----------------------------------------------------|
| `VASTHOUDEN`  | seconden dat de ogen blijven kijken waar je was    |
| `VERSTERKING` | hoe ver de ogen draaien                            |
| `DICHTBIJ`    | vanaf welke gezichtsgrootte je "te dichtbij" bent  |

## Problemen

- **"De webcam geeft geen beeld"**: draait `ogen.py` nog in een ander venster, of gebruikt een ander programma de camera?
- **`cv2` heeft geen `CascadeClassifier`**: je gebruikt OpenCV 5. Activeer de `.venv` of doe `pip install "opencv-python<5"`.

## Meerdere schermen

Heb je meer dan één scherm, dan worden de andere schermen zwart (`schermen.py` start vanzelf).
In het donker duiken gloeiende ogen op die naar het hoofdscherm kijken, en ook daar verschijnen de enge teksten.
Ga je weg, dan zijn er overal ogen. Kom je te dichtbij, dan flitst alles rood.

- Sluiten: `Esc` op een zwart scherm, of stop `ogen.py`.
- Uitzetten: zet `ANDERE_SCHERMEN = False` bovenaan `ogen.py`.
