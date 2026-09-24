#!/usr/bin/env bash
# Keep the disk swapfile as fallback; never reset or format an active swap device.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root' >&2; exit 1; }
modprobe zram
if ! swapon --show=NAME --noheadings | grep -qx /dev/zram0; then
  [[ $(cat /sys/block/zram0/disksize) == 0 ]] || {
    echo 'Refusing to reformat an initialized zram device' >&2
    exit 1
  }
  echo lz4 > /sys/block/zram0/comp_algorithm
  echo 512M > /sys/block/zram0/disksize
  mkswap /dev/zram0
  swapon --priority 100 /dev/zram0
fi
sysctl -w vm.swappiness=100
