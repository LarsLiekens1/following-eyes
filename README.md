# 👁️ Following Eyes

Two creepy, glowing eyes in your terminal that follow you through your webcam.
Bloodshot, with slit pupils and tears of blood. Get too close and they open wide while the lights start to flicker.
Got more than one monitor? The other screens go black and eyes start appearing in the dark.

Everything is calculated live with NumPy and drawn with colored characters (`▀`) in the terminal. No images are loaded.

> The webcam image is only used to find your face. Nothing is recorded, saved or sent anywhere.

## Install

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

Double-click **`start.bat`**: it opens Windows Terminal in fullscreen.

Or in a terminal:

```
python ogen.py          # red eyes
python ogen.py yellow   # or: red, yellow, white
```

Stop with `Ctrl+C` or `Esc`. More detail: zoom out with `Ctrl` + `-`.

## How it works

1. **Webcam:** OpenCV reads the camera in a separate thread.
2. **Finding your face:** [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), a small neural network, finds your face (folder `model/`).
3. **Gaze direction:** the center of your face becomes a number between -1 and 1.
4. **Drawing:** skin, eyelids, sclera, iris and pupil are calculated with math for every pixel.
5. **Terminal:** each `▀` character is 2 pixels (foreground and background color). Only what changes is redrawn.

## Multiple monitors

If you have more than one monitor, the other screens go black (`schermen.py` starts automatically).
Glowing eyes appear in the dark and look toward the main screen, and the creepy messages show up there too.
Walk away and there are eyes everywhere. Get too close and everything flashes red.

- Close: `Esc` on a black screen, or stop `ogen.py`.
- Turn off: set `ANDERE_SCHERMEN = False` at the top of `ogen.py`.

## Settings

At the top of `ogen.py`:

| Setting           | Meaning                                              |
|-------------------|------------------------------------------------------|
| `VASTHOUDEN`      | seconds the eyes keep looking where you last were    |
| `VERSTERKING`     | how far the eyes turn                                |
| `DICHTBIJ`        | face size at which you are "too close"               |
| `ANDERE_SCHERMEN` | black out the other monitors                         |

## Troubleshooting

- **"The webcam is not giving any image"**: is the program still running in another window, or is another app using the camera?
- **`cv2` has no `CascadeClassifier`**: you are using OpenCV 5. Activate the `.venv` or run `pip install "opencv-python<5"`.
