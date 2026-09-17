#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root' >&2; exit 1; }
: "${1:?Path to the reviewed release directory}"
release=$(realpath "$1")
install -d -m 0755 /opt/cardboarddex/operations/scripts/lightsail
install -m 0755 "$release/scripts/lightsail/backup.py" /opt/cardboarddex/operations/scripts/lightsail/backup.py
install -m 0644 "$release/deploy/lightsail/cardboarddex-backup.service" /etc/systemd/system/
install -m 0644 "$release/deploy/lightsail/cardboarddex-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cardboarddex-backup.timer
