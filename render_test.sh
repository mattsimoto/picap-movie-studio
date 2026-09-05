#!/bin/bash
set -u

PROJECT_DIR="$HOME/PiCapMovies/stage2-test"
FRAMES_DIR="$PROJECT_DIR/frames"
MOVIE_PATH="$PROJECT_DIR/movie.mp4"
LOG_PATH="$PROJECT_DIR/render.log"
FPS="${1:-10}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg is not installed"
  exit 1
fi

cd "$FRAMES_DIR" || exit 1
COUNT=$(find . -maxdepth 1 -type f -name 'frame*.jpg' | wc -l)

if [ "$COUNT" -lt 1 ]; then
  echo "ERROR: no frames found"
  exit 1
fi

echo "Rendering $COUNT frames at $FPS FPS..."
echo "FFmpeg: $(command -v ffmpeg)"
echo "Mode: 720p MPEG-4 fast render"
echo "Writing diagnostics to: $LOG_PATH"
rm -f "$LOG_PATH" "$MOVIE_PATH"

set +e
timeout 30 ffmpeg \
  -y \
  -hide_banner \
  -loglevel info \
  -framerate "$FPS" \
  -start_number 1 \
  -i 'frame%04d.jpg' \
  -frames:v "$COUNT" \
  -vf 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2' \
  -c:v mpeg4 \
  -q:v 5 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$MOVIE_PATH" >"$LOG_PATH" 2>&1
RC=$?
set -e

echo "FFmpeg exit code: $RC"

if [ "$RC" -ne 0 ]; then
  echo "---- FFmpeg error log ----"
  tail -n 40 "$LOG_PATH"
  echo "--------------------------"
  exit "$RC"
fi

if [ -s "$MOVIE_PATH" ]; then
  echo "SUCCESS: $MOVIE_PATH"
  ls -lh "$MOVIE_PATH"
else
  echo "ERROR: movie was not created"
  echo "---- FFmpeg log ----"
  tail -n 40 "$LOG_PATH"
  exit 1
fi
