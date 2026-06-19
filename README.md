# CamWatch

Monitors a posterboard via overhead camera and logs when devices (phones, laptops) are removed and replaced.

## Hardware

- Raspberry Pi 4 running the services
- Tapo C113 camera on local network, RTSP stream `stream2`
- White posterboard on the floor with 4 labeled device zones

## Parts

| File | Role |
|---|---|
| `capture.py` | Grabs a single frame from RTSP via ffmpeg |
| `detect_board.py` | Finds the posterboard quad via brightness threshold + contour detection |
| `zones.py` | Subdivides the board into a 2×2 grid, checks occupancy by dark-pixel fraction |
| `db.py` | SQLite event log (present/absent transitions + snapshot path) |
| `monitor.py` | Polling loop — detects board at startup, logs transitions, saves snapshots |
| `web.py` | Flask status page at port 8765 with absence history and snapshot links |
| `camwatch.json` | All config: zone labels, thresholds, poll interval, paths |

## Running

```bash
pip install -r requirements.txt

python monitor.py              # polling loop
python web.py                  # web UI at http://localhost:8765
```

Both take `--config path/to/camwatch.json` to override the default.

## Deploying to the Pi

```bash
export CAMWATCH_HOST=YOUR_PI_HOSTNAME
./sync.sh                      # rsync to the pi (set CAMWATCH_HOST/CAMWATCH_USER to override)
ssh ianrose@${CAMWATCH_HOST}
cd ~/camwatch && ./install-services.sh
```

`install-services.sh` installs and starts both systemd services. After that, to view logs:

```bash
journalctl -u camwatch-monitor -f
journalctl -u camwatch-web -f
```

## Config

Key fields in `camwatch.json`:

- `detection.min_dark_fraction` — fraction of dark pixels that counts as a device present (default `0.08`)
- `monitor.poll_interval_seconds` — how often to check (default `30`)
- `monitor.max_snapshots` — oldest snapshots are pruned beyond this limit (default `50`)
