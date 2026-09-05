#!/bin/bash
set -euo pipefail

PROJECT_DIR="$HOME/PiCapMovies/stage2-test"
FRAMES_DIR="$PROJECT_DIR/frames"
MOVIE_PATH="$PROJECT_DIR/movie.mp4"
FPS="${1:-10}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg is not installed"
  exit 1
fi

cd "$FRAMES_DIR"
COUNT=$(find . -maxdepth 1 -type f -name 'frame*.jpg' | wc -l)

if [ "$COUNT" -lt 1 ]; then
  echo "ERROR: no frames found"
  exit 1
fi

echo "Rendering $COUNT frames at $FPS FPS..."

timeout 60 ffmpeg \
  -y \
  -hide_banner \
  -framerate "$FPS" \
  -start_number 1 \
  -i 'frame%04d.jpg' \
  -frames:v "$COUNT" \
  -c:v libx264 \
  -preset ultrafast \
  -crf 23 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$MOVIE_PATH"

echo
if [ -s "$MOVIE_PATH" ]; then
  echo "SUCCESS: $MOVIE_PATH"
  ls -lh "$MOVIE_PATH"
else
  echo "ERROR: movie was not created"
  exit 1
fi
