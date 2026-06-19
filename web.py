#!/usr/bin/env python3
"""
web.py — simple Flask web app showing device absence history.

Usage:
    python web.py [--config camwatch.json]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, render_template_string, send_from_directory

import db as camdb

app = Flask(__name__)
_config: dict = {}


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CamWatch</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; color: #222; padding: 2rem; }
    h1 { font-size: 1.5rem; margin-bottom: 1.5rem; }
    h2 { font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem; color: #444; text-transform: uppercase; letter-spacing: 0.05em; }

    .currently-missing { margin-bottom: 2rem; }
    .badge-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .badge {
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.4rem 0.8rem; border-radius: 999px;
      font-size: 0.875rem; font-weight: 500;
    }
    .badge.absent  { background: #fee2e2; color: #b91c1c; }
    .badge.present { background: #dcfce7; color: #15803d; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }

    .all-present { color: #15803d; font-style: italic; }

    table { width: 100%; border-collapse: collapse; background: #fff;
            border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
    th { background: #f0f0f0; text-align: left; padding: 0.6rem 1rem;
         font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: #666; }
    td { padding: 0.6rem 1rem; border-top: 1px solid #f0f0f0; font-size: 0.9rem; }
    tr:hover td { background: #fafafa; }
    .duration { font-variant-numeric: tabular-nums; }
    .still-missing { color: #b91c1c; font-weight: 500; }
    .ts { color: #666; font-size: 0.85rem; }
    .img-link { margin-left: 0.4rem; font-size: 0.75rem; color: #888;
                text-decoration: none; border: 1px solid #ccc; border-radius: 3px;
                padding: 0 4px; vertical-align: middle; }
    .img-link:hover { background: #eee; color: #333; }
    .footer { margin-top: 1.5rem; font-size: 0.8rem; color: #999; }
  </style>
</head>
<body>
  <h1>CamWatch — Device Monitor</h1>

  <div class="currently-missing">
    <h2>Current Status</h2>
    {% if current_status %}
      <div class="badge-list">
        {% for item in current_status %}
          <span class="badge {{ item.state }}">
            <span class="dot"></span>
            {{ item.label }}
            {% if item.state == 'absent' %}&nbsp;— missing {{ item.missing_for }}{% endif %}
          </span>
        {% endfor %}
      </div>
    {% else %}
      <p class="all-present">All devices present (or monitor not yet started)</p>
    {% endif %}
  </div>

  <h2>Absence History</h2>
  {% if history %}
  <table>
    <thead>
      <tr>
        <th>Device</th>
        <th>Went Missing</th>
        <th>Returned</th>
        <th>Duration</th>
      </tr>
    </thead>
    <tbody>
      {% for row in history %}
      <tr>
        <td>{{ row.zone_label }}</td>
        <td class="ts">
          <time datetime="{{ row.absent_since_iso }}"></time>
          {% if row.absent_snapshot %}
            <a class="img-link" href="/snapshots/{{ row.absent_snapshot }}" target="_blank">img</a>
          {% endif %}
        </td>
        <td class="ts">
          {% if row.returned_at_iso %}
            <time datetime="{{ row.returned_at_iso }}"></time>
            {% if row.present_snapshot %}
              <a class="img-link" href="/snapshots/{{ row.present_snapshot }}" target="_blank">img</a>
            {% endif %}
          {% else %}—{% endif %}
        </td>
        <td class="duration">
          {% if row.duration_fmt %}
            {{ row.duration_fmt }}
          {% else %}
            <span class="still-missing">still missing</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
    <p style="color:#999; font-style:italic">No absences recorded yet.</p>
  {% endif %}

  <p class="footer">Page rendered at <span id="rendered-at"></span> &nbsp;·&nbsp; Auto-refreshes every 60s</p>
  <meta http-equiv="refresh" content="60">

  <script>
    const FMT = { month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' };
    document.querySelectorAll('time[datetime]').forEach(el => {
      const raw = el.getAttribute('datetime');
      // Ensure JS treats the string as UTC if no offset is present
      const iso = raw.includes('+') || raw.endsWith('Z') ? raw : raw + 'Z';
      el.textContent = new Date(iso).toLocaleString(undefined, FMT);
    });
    document.getElementById('rendered-at').textContent = new Date().toLocaleString(undefined, {...FMT, second: '2-digit'});
  </script>
</body>
</html>
"""


def _to_utc_iso(ts_str: str | None) -> str | None:
    """Normalize a stored timestamp to an unambiguous UTC ISO string for JS Date()."""
    if not ts_str:
        return None
    if not ('+' in ts_str or ts_str.endswith('Z')):
        ts_str = ts_str + 'Z'
    return ts_str


def _fmt_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m"


def _missing_for(absent_since: str) -> str:
    try:
        dt = datetime.fromisoformat(absent_since)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = int((datetime.now(timezone.utc) - dt).total_seconds())
        return _fmt_duration(delta) or "just now"
    except Exception:
        return "?"


@app.route("/snapshots/<path:filename>")
def snapshot(filename):
    snapshots_dir = Path(_config["monitor"]["snapshots_dir"]).resolve()
    return send_from_directory(snapshots_dir, filename)


@app.route("/")
def index():
    db_path = _config["monitor"]["db_path"]

    # Current status — one badge per zone
    zone_cfgs = _config["zones"]
    current_db_state = camdb.get_current_state(db_path)
    current_status = []
    for z in zone_cfgs:
        state = current_db_state.get(z["id"], "unknown")
        if state == "unknown":
            continue
        entry = {"label": z["label"], "state": state}
        if state == "absent":
            # Find the most recent absent event for this zone to compute duration
            history = camdb.get_absence_history(db_path, limit=500)
            ongoing = next((r for r in history if r["zone_id"] == z["id"] and r["returned_at"] is None), None)
            entry["missing_for"] = _missing_for(ongoing["absent_since"]) if ongoing else "?"
        current_status.append(entry)

    # History
    raw_history = camdb.get_absence_history(db_path)
    history = [
        {
            **row,
            "absent_since_iso": _to_utc_iso(row["absent_since"]),
            "returned_at_iso":  _to_utc_iso(row["returned_at"]),
            "duration_fmt":     _fmt_duration(row["duration_seconds"]),
            "absent_snapshot":  row["absent_snapshot"],
            "present_snapshot": row["present_snapshot"],
        }
        for row in raw_history
    ]

    return render_template_string(PAGE_TEMPLATE,
                                  current_status=current_status,
                                  history=history)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="camwatch.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    _config.update(config)

    camdb.init_db(config["monitor"]["db_path"])

    port = config["monitor"]["web_port"]
    print(f"CamWatch web running at http://localhost:{port}/")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
