#!/bin/bash
# Run this on the Pi once to install and enable both systemd services.
set -e

UNIT_DIR=/etc/systemd/system
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo cp "$SCRIPT_DIR/camwatch-monitor.service" "$UNIT_DIR/"
sudo cp "$SCRIPT_DIR/camwatch-web.service"     "$UNIT_DIR/"

sudo systemctl daemon-reload
sudo systemctl enable camwatch-monitor camwatch-web
sudo systemctl start  camwatch-monitor camwatch-web

echo ""
echo "Services installed and started."
echo "  Monitor logs:  journalctl -u camwatch-monitor -f"
echo "  Web logs:      journalctl -u camwatch-web -f"
echo "  Web interface: http://$(hostname -I | awk '{print $1}'):8765/"
