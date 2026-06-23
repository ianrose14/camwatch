#!/usr/bin/env python3
"""
detect_board.py — locate the white posterboard in a frame and output its 4 corners.

Approach: threshold for bright pixels, find largest contour, fit a 4-point polygon.
Saves a debug image with the detected quad drawn on it.

Usage:
    python detect_board.py [--input snapshot.jpg] [--output debug_board.jpg]
"""

import argparse
import sys

import cv2
import numpy as np


def find_board_quad(frame: np.ndarray, brightness_thresh: int = 200) -> np.ndarray | None:
    """
    Return the 4 corners of the white posterboard as an (4,2) int array,
    ordered [top-left, top-right, bottom-right, bottom-left].
    Returns None if no confident quad found.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Threshold: keep only very bright pixels (the white board)
    _, mask = cv2.threshold(gray, brightness_thresh, 255, cv2.THRESH_BINARY)

    # Small open removes noise; no close — convex hull bridges device holes,
    # and close would merge nearby cable blobs into the board contour.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Largest contour should be the board
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    frame_area = frame.shape[0] * frame.shape[1]
    if area < frame_area * 0.05:  # sanity check: board should be >5% of frame
        print(f"Largest contour too small ({area:.0f}px, {100*area/frame_area:.1f}% of frame)", file=sys.stderr)
        return None

    # Convex hull spans across dark devices sitting on the board so the
    # polygon approximation sees the true outer boundary, not a C-shape.
    hull = cv2.convexHull(largest)

    # Approximate to a polygon; keep loosening epsilon until we get 4 sides
    peri = cv2.arcLength(hull, True)
    for eps_factor in [0.02, 0.04, 0.06, 0.08, 0.10]:
        approx = cv2.approxPolyDP(hull, eps_factor * peri, True)
        if len(approx) == 4:
            break
    else:
        print(f"Could not approximate to 4 corners (got {len(approx)})", file=sys.stderr)
        return None

    pts = approx.reshape(4, 2).astype(np.float32)
    return _order_points(pts)


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points: top-left, top-right, bottom-right, bottom-left."""
    ordered = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    ordered[0] = pts[np.argmin(s)]   # top-left: smallest x+y
    ordered[2] = pts[np.argmax(s)]   # bottom-right: largest x+y
    diff = np.diff(pts, axis=1)
    ordered[1] = pts[np.argmin(diff)]  # top-right: smallest y-x
    ordered[3] = pts[np.argmax(diff)]  # bottom-left: largest y-x
    return ordered.astype(np.int32)


def draw_quad(frame: np.ndarray, quad: np.ndarray) -> np.ndarray:
    out = frame.copy()
    cv2.polylines(out, [quad.reshape(-1, 1, 2)], isClosed=True, color=(0, 255, 0), thickness=3)
    labels = ["TL", "TR", "BR", "BL"]
    for (x, y), label in zip(quad, labels):
        cv2.circle(out, (x, y), 8, (0, 0, 255), -1)
        cv2.putText(out, f"{label} ({x},{y})", (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="snapshot.jpg")
    parser.add_argument("--output", default="debug_board.jpg")
    parser.add_argument("--brightness", type=int, default=200,
                        help="Brightness threshold for white detection (0-255)")
    args = parser.parse_args()

    frame = cv2.imread(args.input)
    if frame is None:
        sys.exit(f"Could not read {args.input}")

    quad = find_board_quad(frame, brightness_thresh=args.brightness)
    if quad is None:
        sys.exit("Board not detected. Try adjusting --brightness.")

    print("Board corners (TL, TR, BR, BL):")
    for label, (x, y) in zip(["TL", "TR", "BR", "BL"], quad):
        print(f"  {label}: ({x}, {y})")

    debug = draw_quad(frame, quad)
    cv2.imwrite(args.output, debug)
    print(f"Debug image saved to {args.output}")


if __name__ == "__main__":
    main()
