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


## Google Drive export (PiCap Movie Studio)

PiCap can automatically upload an exported movie after **MAKE MOVIE** finishes.
From **MY MOVIES**, select a project and tap **EXPORT TO DRIVE** to send it
again or send an older movie. Tap **DRIVE FOLDER** to enter a different destination
folder using PiCap's built-in touchscreen keyboard. The default is
`My Drive / PiCap Movies`.

Google sign-in is a one-time **parent setup**. PiCap uses
[rclone](https://rclone.org/drive/) and expects a Google Drive rclone remote
**named `picapdrive`**. PiCap itself does not store your Google password,
access tokens, or OAuth client secrets.

1. On the Raspberry Pi (via SSH from a computer if there is no physical keyboard):
   `sudo apt update && sudo apt install -y rclone`
2. Follow the current [Google Drive remote configuration guide](https://rclone.org/drive/):
   run `rclone config`, create a remote called `picapdrive`, and select the
   `drive` storage backend. As of 2026, rclone's shared Google client ID is being
   retired; follow the guide to create your **own OAuth client ID and secret**.
   If using `drive.file` scope, rclone can see only files/folders it creates:
   allow PiCap to create its destination folder on first upload. An existing
   folder created outside rclone may require the full `drive` scope instead.
3. Complete Google authorization in a browser on the Pi, or follow
   [rclone's remote/headless setup](https://rclone.org/remote_setup/) if you
   authorize on another computer. Keep OAuth tokens **out of GitHub and chats**.
4. Test the connection with `rclone mkdir "picapdrive:PiCap Movies"`.
   Then restart PiCap and export a movie. Check the Drive folder from another
   device before deleting any local project.

Exports are queued without freezing the touchscreen. PiCap retains the original
movie and every JPEG frame on the Pi, even if the connection fails. Failed
uploads can be retried from MY MOVIES. Leave PiCap running until the status
says **Uploaded**; a reboot or app exit can interrupt a transfer.

**Video-format caveat:** Current PiCap outputs MJPEG AVI, which can freeze on
the first frame in some VLC/Drive players. The in-app player plays the original
JPEG frames, but uploading that AVI does *not* fix its compatibility. Drive
export can also upload MP4 files if a future renderer creates one. Confirm the
uploaded file actually plays before treating it as a finished distributable
video.


## Phone transfer with a QR code (no Google account on the Pi)

From **MY MOVIES**, select a movie that has already been rendered and tap
**PHONE QR**. PiCap displays a fresh QR code for that movie. Scan it with your
phone's camera and choose **Download** in the phone browser. The file is copied
straight from the Raspberry Pi to your phone across your local network.
You can then use your phone's Share menu to save the file in Google Drive.

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
finished export. Direct export to Google Drive remains a separate option
that uses rclone.
