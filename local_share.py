"""One-tap temporary LAN sharing for individual PiCap movies.

This deliberately does not publish videos to the internet, use cloud credentials,
or expose the movie-project folders. A fresh random link expires after 20 minutes.
The phone and Pi must be reachable on the same local network.
"""
import re
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PORT = 8765
LINK_SECONDS = 20 * 60


def lan_ip():
    """Prefer the active interface's IPv4 address, even when Pi uses Ethernet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        address = sock.getsockname()[0]
        if address and not address.startswith("127.") and not address.startswith("169.254."):
            return address
    except OSError:
        pass
    finally:
        sock.close()

    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=2, check=True
        )
        for address in result.stdout.split():
            if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", address) and not (
                address.startswith("127.") or address.startswith("169.254.")
            ):
                return address
    except (OSError, subprocess.SubprocessError):
        pass
    raise RuntimeError("No local IPv4 address. Connect the Pi and phone to the same network.")


class LocalMovieServer:
    """Serve explicitly selected files, not a browsable directory or public website."""

    def __init__(self):
        self.lock = threading.Lock()
        self.links = {}
        self.server = None
        self.thread = None

    def start(self):
        if self.server is not None:
            return
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_movie(head_only=False)

            def do_HEAD(self):
                self.send_movie(head_only=True)

            def send_movie(self, head_only):
                route = urlsplit(self.path).path
                if not route.startswith("/download/"):
                    self.send_error(404)
                    return
                token = route[len("/download/"):]
                if not token or "/" in token:
                    self.send_error(404)
                    return
                with owner.lock:
                    item = owner.links.get(token)
                if item is None:
                    self.send_error(404, "Share link not found")
                    return
                movie_path, expires_at = item
                if time.monotonic() >= expires_at:
                    with owner.lock:
                        owner.links.pop(token, None)
                    self.send_error(410, "This QR code has expired")
                    return

                try:
                    # Only the saved video path explicitly issued by PiCap is served.
                    with movie_path.open("rb") as movie:
                        file_size = movie_path.stat().st_size
                        if not file_size:
                            self.send_error(404, "Movie is empty")
                            return
                        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", movie_path.parent.name)
                        download_name = (stem or "PiCap-Movie") + movie_path.suffix.lower()
                        media_type = (
                            "video/mp4" if movie_path.suffix.lower() == ".mp4"
                            else "video/x-msvideo"
                        )
                        self.send_response(200)
                        self.send_header("Content-Type", media_type)
                        self.send_header(
                            "Content-Disposition", f'attachment; filename="{download_name}"'
                        )
                        self.send_header("Content-Length", str(file_size))
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.end_headers()
                        if not head_only:
                            while True:
                                block = movie.read(256 * 1024)
                                if not block:
                                    break
                                self.wfile.write(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Phone cancelled its download.
                except OSError:
                    try:
                        self.send_error(404, "Movie no longer available")
                    except OSError:
                        pass

            def log_message(self, _format, *_args):
                # Do not print the private share token into kiosk terminal logs.
                pass

        class ShareHTTPServer(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.server = ShareHTTPServer(("0.0.0.0", PORT), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="PiCapMovieShare", daemon=True
        )
        self.thread.start()

    def share(self, movie_path):
        file_path = Path(movie_path).resolve(strict=True)
        if not file_path.is_file() or file_path.suffix.lower() not in (".mp4", ".avi"):
            raise ValueError("Select a completed movie before sharing.")
        if file_path.stat().st_size <= 0:
            raise ValueError("The saved movie is empty.")
        address = lan_ip()
        self.start()
        token = secrets.token_urlsafe(24)
        expires_at = time.monotonic() + LINK_SECONDS
        with self.lock:
            self.links = {
                key: value for key, value in self.links.items()
                if value[1] > time.monotonic()
            }
            self.links[token] = (file_path, expires_at)
        return f"http://{address}:{PORT}/download/{token}"

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.thread = None
        with self.lock:
            self.links.clear()
