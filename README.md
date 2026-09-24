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


## Phone transfer with a QR code

From **MY MOVIES**, select a movie that has already been rendered and tap
**PHONE QR**. PiCap displays a fresh QR code for that movie. Scan it with your
phone's camera and choose **Download** in the phone browser. The file is copied
straight from the Raspberry Pi to your phone across your local network.
You can then save or share the downloaded movie from your phone.

One-time Raspberry Pi dependency:

```bash
sudo apt update
sudo apt install -y python3-qrcode python3-pil
```

The Pi can be plugged into the router using Ethernet while your phone uses
Wi-Fi. Both must be on the **same reachable local network** (guest Wi-Fi and
client-isolation modes can prevent access). Leave PiCap running until the
download finishes. The QR code includes the Pi's LAN IPv4 address and port
`8765`, so the IP address may change if you move to a different network.
If the Pi's firewall blocks incoming connections, allow TCP port 8765 **on
your trusted local network only**; never port-forward it on your router.

Each scan link has a strong random token and expires after 20 minutes. PiCap
only serves the selected completed video file, not the project folders.
It does not upload to the internet; it runs a temporary, unencrypted
HTTP download service on your local network. Anyone with the QR code
and network access during that period can download that movie. To stop
sharing, exit PiCap. Do not display QR codes for sensitive recordings on
untrusted networks.

**Current video compatibility:** QR transfer copies the actual exported file
unchanged. Today's AVI exports can freeze in some external players, even
though PiCap's internal gallery player displays the original still frames.
The QR feature does **not** convert AVI to MP4 or repair old files.
Confirm a downloaded movie plays on your phone before relying on it as a
finished export.


## Add voices with a USB microphone

PiCap's **MY MOVIES → ADD VOICES** workflow records one continuous narration
take over an existing completed movie. Plug a USB microphone into the Pi and
install the audio tools and MP4 encoder:

```bash
sudo apt update
sudo apt install -y alsa-utils ffmpeg
```

Tap **ADD VOICES** for a movie after making it. Tap **RECORD VOICES** and speak
as the still pictures play. Recording automatically finishes when the full
movie has played (rounded to the next whole second to let ALSA finish writing
WAV). The take is stored as `narration.wav` alongside the movie's JPG frames.
Tap **PLAY TAKE** to watch the pictures while hearing the voice track through
the Pi's configured speaker/headphones; the USB mic alone does not provide
audio output. Tap **RECORD VOICES** again to redo the whole track. Cancelling
a retake preserves the previous recording.

Tap **SAVE MP4** to render a separate 640×360 H.264/AAC `movie.mp4` with
the voices embedded. Rendering runs in a separate FFmpeg process; allow time
on the Pi 3B+. This step leaves the original JPEG frames, narration WAV and
old AVI unchanged. A failed export does not replace an existing MP4.
Once saved, use **MY MOVIES → PHONE QR** to download the latest completed
movie; PiCap's **WATCH** screen also plays an up-to-date saved narration track.

If the capture device is not found, run `arecord -l` and verify that the USB
mic is listed. PiCap normally selects an ALSA capture device automatically.
To override unusual hardware, set `PICAP_MIC_DEVICE` (for example,
`plughw:1,0`) in the PiCap launcher environment before starting the app.
Confirm the Pi's playback audio output works when testing PLAY TAKE.

This first version records one continuous voice track; individual dialogue
clips, separate sound-effects tracks and background music can be added later.
If frames or movie FPS are changed after a take, record a fresh take and
SAVE MP4 again before sharing. Never delete local projects until the MP4
plays and the phone transfer has been verified.
