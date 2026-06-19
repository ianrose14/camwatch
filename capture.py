#!/usr/bin/env python3
"""
capture.py — grab a single frame from the Tapo RTSP stream and save it.
Run this first to verify the camera pipeline works before adding zone detection.

Usage:
    python capture.py [--output PATH]
"""

import argparse
import subprocess
import sys
import tempfile
import os

import cv2
import numpy as np


RTSP_URL = "rtsp://ianrose:ianrose1@192.168.4.99/stream2"


def grab_frame(rtsp_url: str) -> np.ndarray:
    """Pull one frame from the RTSP stream via ffmpeg, return as BGR numpy array."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-i", rtsp_url,
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                tmp_path,
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            print("ffmpeg stderr:", result.stderr.decode(), file=sys.stderr)
            raise RuntimeError(f"ffmpeg exited with code {result.returncode}")

        frame = cv2.imread(tmp_path)
        if frame is None:
            raise RuntimeError("cv2.imread returned None — bad output file?")
        return frame
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Grab one frame from the RTSP stream.")
    parser.add_argument("--output", default="snapshot.jpg", help="Where to save the frame")
    args = parser.parse_args()

    print(f"Reaching out to {RTSP_URL} ...")
    frame = grab_frame(RTSP_URL)
    h, w = frame.shape[:2]
    print(f"Got frame: {w}x{h}")

    cv2.imwrite(args.output, frame)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
