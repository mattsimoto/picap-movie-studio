# PiCap Movie Studio

A kid-friendly stop-motion movie studio built for a Raspberry Pi 3B+, 7-inch touchscreen, and Raspberry Pi Camera.

The project is being built one stage at a time so each stage is usable and testable before the next one is added.

## Build stages

1. **Camera works** — live touchscreen camera preview and save one photo.
2. **Stop-motion works** — numbered frame capture and an Oops/undo-last-frame control.
3. **Animation works** — onion skinning, instant playback, and FPS selection.
4. **Movies work** — render a project to MP4 with FFmpeg.
5. **Editing works** — frame browser, delete, duplicate, hold frames, titles, and sound.
6. **Kid polish** — large icons, friendly project screens, sounds, and visual polish.
7. **Physical controls** — GPIO-connected capture/play/undo controls on the wooden studio box.

## Current stage

### Stage 1 — Camera works

Goal: prove that the Pi, touchscreen, and camera work together before we build anything else.

Stage 1 provides:

- full-screen live camera preview
- large touchscreen **TAKE PICTURE** button
- large **EXIT** button
- automatic photo filenames using date/time
- saved photos in `~/PiCapMovies/camera-test/`
- brief on-screen confirmation after capture

## Recommended Pi software

Use Raspberry Pi OS with the desktop environment. The application uses the modern Raspberry Pi camera stack through Picamera2.

Install Stage 1 dependencies:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-pyqt5
```

Test the camera before running PiCap Movie Studio:

```bash
rpicam-hello
```

If you see the camera preview, close it and continue.

## Run Stage 1

Clone the repository:

```bash
git clone https://github.com/mattsimoto/picap-movie-studio.git
cd picap-movie-studio
```

Run the app:

```bash
python3 app.py
```

Tap **TAKE PICTURE**. The image will be stored in:

```text
/home/<your-user>/PiCapMovies/camera-test/
```

## Stage 1 test checklist

Do not move on to Stage 2 until all five items work:

- [ ] Raspberry Pi boots normally with the 7-inch touchscreen.
- [ ] Touch input works.
- [ ] `rpicam-hello` shows a live camera image.
- [ ] `python3 app.py` shows the PiCap live preview.
- [ ] Tapping **TAKE PICTURE** saves a JPEG successfully.

Once those work, Stage 2 will turn this camera test into the first real stop-motion capture screen.
