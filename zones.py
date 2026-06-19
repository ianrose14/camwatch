#!/usr/bin/env python3
"""
zones.py — zone definition and occupancy detection.

Divides the detected board quad into a 2x2 grid of zones and checks each
for device presence by counting dark pixels against the white board background.

Usage (standalone test):
    python zones.py [--input snapshot.jpg] [--output debug_zones.jpg] [--config camwatch.json]
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Zone:
    id: str
    label: str
    poly: np.ndarray  # (4,2) int32, order: TL, TR, BR, BL


@dataclass
class ZoneResult:
    zone: Zone
    occupied: bool
    dark_fraction: float


def _lerp(p1, p2, t):
    return (
        int(p1[0] + t * (p2[0] - p1[0])),
        int(p1[1] + t * (p2[1] - p1[1])),
    )


def zones_from_quad(quad: np.ndarray, config: dict) -> list[Zone]:
    """Build Zone objects from a detected board quad (4x2 array: TL, TR, BR, BL)."""
    tl, tr, br, bl = tuple(quad[0]), tuple(quad[1]), tuple(quad[2]), tuple(quad[3])

    top_mid   = _lerp(tl, tr, 0.5)
    bot_mid   = _lerp(bl, br, 0.5)
    left_mid  = _lerp(tl, bl, 0.5)
    right_mid = _lerp(tr, br, 0.5)
    center    = _lerp(top_mid, bot_mid, 0.5)

    # Raw corners [TL, TR, BR, BL] for each 2x2 quadrant
    raw = [
        (tl,       top_mid,   center,    left_mid ),  # top-left
        (top_mid,  tr,        right_mid, center   ),  # top-right
        (left_mid, center,    bot_mid,   bl       ),  # bottom-left
        (center,   right_mid, br,        bot_mid  ),  # bottom-right
    ]

    inset = config["detection"]["zone_inset"]
    zones = []
    for zone_cfg, corners in zip(config["zones"], raw):
        pts = np.array(corners, dtype=np.float32)
        centroid = pts.mean(axis=0)
        pts = pts + inset * (centroid - pts)
        zones.append(Zone(
            id=zone_cfg["id"],
            label=zone_cfg["label"],
            poly=pts.astype(np.int32),
        ))

    return zones


def zones_from_config(config: dict) -> list[Zone]:
    """Build Zone objects from a board_quad stored in config (legacy/testing path)."""
    q = config["board_quad"]
    quad = np.array([q["TL"], q["TR"], q["BR"], q["BL"]], dtype=np.int32)
    return zones_from_quad(quad, config)


def check_zone(frame: np.ndarray, zone: Zone, dark_threshold: int, min_dark_fraction: float) -> ZoneResult:
    """Return occupancy result for a single zone."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(gray.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [zone.poly.reshape(-1, 1, 2)], 255)

    zone_pixels = gray[mask == 255]
    if len(zone_pixels) == 0:
        return ZoneResult(zone=zone, occupied=False, dark_fraction=0.0)

    dark_fraction = float((zone_pixels < dark_threshold).sum()) / len(zone_pixels)
    occupied = dark_fraction >= min_dark_fraction
    return ZoneResult(zone=zone, occupied=occupied, dark_fraction=dark_fraction)


def check_all_zones(frame: np.ndarray, zones: list[Zone], config: dict) -> list[ZoneResult]:
    thresh = config["detection"]["dark_threshold"]
    min_frac = config["detection"]["min_dark_fraction"]
    return [check_zone(frame, z, thresh, min_frac) for z in zones]


def draw_zones(frame: np.ndarray, results: list[ZoneResult],
               highlight_id: str | None = None, board_quad: np.ndarray | None = None) -> np.ndarray:
    out = frame.copy()

    if board_quad is not None:
        cv2.polylines(out, [board_quad.reshape(-1, 1, 2)], isClosed=True,
                      color=(255, 200, 0), thickness=1)

    for r in results:
        is_highlight = r.zone.id == highlight_id
        color = (0, 200, 0) if r.occupied else (0, 0, 220)
        thickness = 3 if is_highlight else 2
        cv2.polylines(out, [r.zone.poly.reshape(-1, 1, 2)], isClosed=True, color=color, thickness=thickness)
        cx, cy = r.zone.poly.mean(axis=0).astype(int)
        status = "PRESENT" if r.occupied else "ABSENT"
        cv2.putText(out, r.zone.label, (cx - 40, cy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        cv2.putText(out, f"{status} ({r.dark_fraction:.2%})", (cx - 50, cy + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    if highlight_id:
        r = next((r for r in results if r.zone.id == highlight_id), None)
        if r:
            action = "RETURNED" if r.occupied else "REMOVED"
            label = f"{r.zone.label}: {action}"
            cv2.putText(out, label, (10, out.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 3)
            cv2.putText(out, label, (10, out.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220) if not r.occupied else (0, 200, 0), 2)

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="snapshot.jpg")
    parser.add_argument("--output", default="debug_zones.jpg")
    parser.add_argument("--config", default="camwatch.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    config = json.loads(config_path.read_text())

    frame = cv2.imread(args.input)
    if frame is None:
        sys.exit(f"Could not read {args.input}")

    from detect_board import find_board_quad
    brightness = config["detection"].get("brightness_threshold", 200)
    quad = find_board_quad(frame, brightness_thresh=brightness)
    if quad is None:
        sys.exit("Board not detected in image. Check brightness_threshold in config.")

    zones = zones_from_quad(quad, config)
    results = check_all_zones(frame, zones, config)

    for r in results:
        status = "PRESENT" if r.occupied else "absent"
        print(f"  {r.zone.label:<12} {status}  (dark={r.dark_fraction:.2%})")

    debug = draw_zones(frame, results, board_quad=quad)
    cv2.imwrite(args.output, debug)
    print(f"\nDebug image saved to {args.output}")


if __name__ == "__main__":
    main()
