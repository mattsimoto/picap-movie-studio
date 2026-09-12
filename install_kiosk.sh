#!/bin/bash
set -euo pipefail

APP_DIR="$HOME/picap-movie-studio"
PYTHON="$(command -v python3)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_DIR="$HOME/Desktop"

mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/picap-movie-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PiCap Movie Studio
Comment=Kid-friendly stop motion studio
Exec=$PYTHON $APP_DIR/studio.py
Path=$APP_DIR
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

if [ -d "$DESKTOP_DIR" ]; then
  cat > "$DESKTOP_DIR/PiCap-Movie-Studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PiCap Movie Studio
Comment=Kid-friendly stop motion studio
Exec=$PYTHON $APP_DIR/studio.py
Path=$APP_DIR
Terminal=false
Icon=camera-photo
EOF
  chmod +x "$DESKTOP_DIR/PiCap-Movie-Studio.desktop"
fi

echo "PiCap Movie Studio will now open automatically after desktop login."
echo "A desktop launcher was also created when a Desktop folder was available."
