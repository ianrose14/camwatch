#!/usr/bin/env python3
"""
monitor.py — polls the camera, detects zone occupancy, logs state changes to SQLite.

Logs an event only when a zone's state changes (present→absent or absent→present).
Saves a debug snapshot image for every transition.
Camera errors are skipped silently (no false 'absent' events from a dropped frame).

Usage:
    python monitor.py [--config camwatch.json]
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from capture import grab_frame, RTSP_URL
from db import init_db, log_event, get_current_state
from detect_board import find_board_quad
from zones import zones_from_quad, check_all_zones, draw_zones

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)



def save_snapshot(frame: np.ndarray, results, zone_id: str,
                  snapshots_dir: Path, ts: datetime, config: dict) -> str:
    """Save a debug-annotated snapshot for a transition event. Returns the filename."""
    snapshots_dir.mkdir(exist_ok=True)
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    filename = f"{ts_str}_{zone_id}.jpg"
    path = snapshots_dir / filename

    board_quad = config.get("_board_quad")  # injected at startup
    debug = draw_zones(frame, results, highlight_id=zone_id, board_quad=board_quad)
    cv2.imwrite(str(path), debug)
    return filename


def prune_snapshots(snapshots_dir: Path, max_count: int) -> None:
    """Delete oldest snapshots if the directory exceeds max_count files."""
    files = sorted(snapshots_dir.glob("*.jpg"))
    for old in files[:-max_count] if len(files) > max_count else []:
        old.unlink()
        log.debug("Pruned snapshot %s", old.name)


def poll_once(rtsp_url: str, config: dict, db_path: str,
              snapshots_dir: Path, known_state: dict[str, str]) -> dict[str, str]:
    """
    Grab a frame, detect board, check zones, log any state changes.
    Returns updated known_state (unchanged on camera error).
    """
    try:
        frame = grab_frame(rtsp_url)
    except Exception as e:
        log.warning("Camera grab failed, skipping poll: %s", e)
        return known_state

    brightness = config["detection"].get("brightness_threshold", 200)
    quad = find_board_quad(frame, brightness_thresh=brightness)
    if quad is None:
        log.warning("Board not detected this poll, skipping")
        return known_state
    config["_board_quad"] = quad
    zones = zones_from_quad(quad, config)

    results = check_all_zones(frame, zones, config)
    now = datetime.now(timezone.utc)
    max_snapshots = config["monitor"]["max_snapshots"]

    for r in results:
        new_state = "present" if r.occupied else "absent"
        prev_state = known_state.get(r.zone.id)

        if new_state != prev_state:
            log.info("%-14s  %s → %s  (dark=%.2f%%)",
                     r.zone.label,
                     prev_state or "unknown",
                     new_state,
                     r.dark_fraction * 100)
            filename = save_snapshot(frame, results, r.zone.id, snapshots_dir, now, config)
            prune_snapshots(snapshots_dir, max_snapshots)
            log_event(db_path, r.zone.id, r.zone.label, new_state, ts=now, snapshot_path=filename)
            known_state[r.zone.id] = new_state

    return known_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="camwatch.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    config = json.loads(config_path.read_text())

    db_path = config["monitor"]["db_path"]
    poll_interval = config["monitor"]["poll_interval_seconds"]
    snapshots_dir = Path(config["monitor"]["snapshots_dir"])
    rtsp_url = config.get("rtsp_url", RTSP_URL)

    init_db(db_path)

    log.info("camwatch monitor starting — polling every %ds", poll_interval)

    # Seed known_state from DB so restarts don't re-log unchanged state
    known_state = get_current_state(db_path)
    log.info("Restored state from DB: %s", known_state or "(empty — first run)")

    while True:
        known_state = poll_once(rtsp_url, config, db_path, snapshots_dir, known_state)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
