#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root' >&2; exit 1; }
repo=$(cd "$(dirname "$0")/../.." && pwd)
memory_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
if (( memory_kb > 600000 )); then
  echo 'Compressed swap setup is only needed on the 512 MB host.'
  exit 0
fi
install -d -m 0755 /opt/cardboarddex/operations/scripts/lightsail
install -m 0755 "$repo/scripts/lightsail/zram.sh" /opt/cardboarddex/operations/scripts/lightsail/zram.sh
install -m 0644 "$repo/deploy/lightsail/cardboarddex-zram.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cardboarddex-zram.service
