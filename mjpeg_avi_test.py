#!/usr/bin/env python3
from pathlib import Path
import struct
import sys

PROJECT_DIR = Path.home() / "PiCapMovies" / "stage2-test"
FRAMES_DIR = PROJECT_DIR / "frames"
OUTPUT = PROJECT_DIR / "movie.avi"
FPS = int(sys.argv[1]) if len(sys.argv) > 1 else 10


def jpeg_size(path: Path):
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError(f"Not a JPEG: {path.name}")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9):
            continue
        if i + 2 > len(data):
            break
        seglen = int.from_bytes(data[i:i+2], "big")
        if seglen < 2 or i + seglen > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if seglen < 7:
                break
            height = int.from_bytes(data[i+3:i+5], "big")
            width = int.from_bytes(data[i+5:i+7], "big")
            return width, height
        i += seglen
    raise ValueError(f"Could not read JPEG dimensions: {path.name}")


def chunk(tag: bytes, payload: bytes) -> bytes:
    pad = b"\x00" if len(payload) & 1 else b""
    return tag + struct.pack("<I", len(payload)) + payload + pad


def list_chunk(list_type: bytes, payload: bytes) -> bytes:
    body = list_type + payload
    return b"LIST" + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b"")


def write_mjpeg_avi(frames, output: Path, fps: int):
    width, height = jpeg_size(frames[0])
    frame_data = []
    max_frame = 0
    for f in frames:
        w, h = jpeg_size(f)
        if (w, h) != (width, height):
            raise ValueError(f"Frame size mismatch: {f.name} is {w}x{h}, expected {width}x{height}")
        data = f.read_bytes()
        frame_data.append(data)
        max_frame = max(max_frame, len(data))

    total_frames = len(frame_data)
    microsec_per_frame = round(1_000_000 / fps)

    # Main AVI header (AVIMAINHEADER, 56 bytes)
    avih = struct.pack(
        "<IIIIIIIIII4I",
        microsec_per_frame,
        0,
        0,
        0x10,  # AVIF_HASINDEX
        total_frames,
        0,
        1,
        max_frame,
        width,
        height,
        0, 0, 0, 0,
    )

    # Stream header (AVISTREAMHEADER, 56 bytes)
    strh = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"MJPG",
        0,
        0,
        0,
        0,
        1,
        fps,
        0,
        total_frames,
        max_frame,
        0xFFFFFFFF,
        0,
        0,
        0,
        width,
        height,
    )

    # BITMAPINFOHEADER (40 bytes)
    strf = struct.pack(
        "<IiiHH4sIiiII",
        40,
        width,
        height,
        1,
        24,
        b"MJPG",
        width * height * 3,
        0,
        0,
        0,
        0,
    )

    strl = list_chunk(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf))
    hdrl = list_chunk(b"hdrl", chunk(b"avih", avih) + strl)

    movi_payload = bytearray()
    index_entries = bytearray()
    # AVI idx1 offsets are relative to the start of the movi list contents after 'movi'.
    offset = 4
    for data in frame_data:
        ck = chunk(b"00dc", data)
        movi_payload.extend(ck)
        index_entries.extend(struct.pack("<4sIII", b"00dc", 0x10, offset, len(data)))
        offset += len(ck)

    movi = list_chunk(b"movi", bytes(movi_payload))
    idx1 = chunk(b"idx1", bytes(index_entries))
    riff_body = b"AVI " + hdrl + movi + idx1
    output.write_bytes(b"RIFF" + struct.pack("<I", len(riff_body)) + riff_body)
    return width, height, total_frames


def main():
    frames = sorted(FRAMES_DIR.glob("frame*.jpg"))
    if not frames:
        print("ERROR: no frames found")
        return 1
    print(f"Found {len(frames)} frames")
    print("Renderer: pure Python MJPEG AVI (no FFmpeg, no re-encoding)")
    try:
        width, height, count = write_mjpeg_avi(frames, OUTPUT, FPS)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"SUCCESS: {OUTPUT}")
    print(f"{count} frames, {width}x{height}, {FPS} FPS")
    print(f"Size: {OUTPUT.stat().st_size / (1024*1024):.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
