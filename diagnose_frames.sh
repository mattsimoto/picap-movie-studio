#!/bin/bash
set -u

PROJECT_DIR="$HOME/PiCapMovies/stage2-test"
FRAMES_DIR="$PROJECT_DIR/frames"

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ERROR: ffprobe is not installed (it normally comes with ffmpeg)."
  exit 1
fi

cd "$FRAMES_DIR" || exit 1

shopt -s nullglob
frames=(frame*.jpg)
if [ ${#frames[@]} -eq 0 ]; then
  echo "ERROR: no frames found"
  exit 1
fi

echo "Found ${#frames[@]} frames."
echo "Checking each JPEG with ffprobe (5-second limit each)..."
echo

bad=0
for f in "${frames[@]}"; do
  printf "%-18s " "$f"
  out=$(timeout 5 ffprobe -v error -select_streams v:0 \
    -show_entries stream=codec_name,width,height,pix_fmt \
    -of csv=p=0 "$f" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    echo "OK  $out"
  elif [ $rc -eq 124 ]; then
    echo "TIMEOUT"
    bad=1
  else
    echo "ERROR (code $rc): $out"
    bad=1
  fi
done

echo
if [ $bad -ne 0 ]; then
  echo "One or more source frames are bad or unreadable."
  echo "Stop here and send a photo of this output."
  exit 2
fi

echo "All frames passed ffprobe."
echo
echo "Testing FFmpeg on ONE frame only..."
set +e
timeout 10 ffmpeg -y -hide_banner -loglevel error \
  -i "${frames[0]}" -frames:v 1 -f null -
rc=$?
set -e

echo "Single-frame FFmpeg exit code: $rc"

if [ $rc -eq 0 ]; then
  echo "SINGLE FRAME TEST PASSED"
elif [ $rc -eq 124 ]; then
  echo "SINGLE FRAME TEST TIMED OUT"
else
  echo "SINGLE FRAME TEST FAILED"
fi
