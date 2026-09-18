#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run bootstrap as root' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg python3-boto3 python3-dotenv unzip
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu
install -d -m 0750 -o root -g ubuntu /etc/cardboarddex
install -d -o ubuntu -g ubuntu /opt/cardboarddex/releases
if ! swapon --show=NAME --noheadings | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
printf 'vm.swappiness=10\n' > /etc/sysctl.d/90-cardboarddex.conf
sysctl --system > /dev/null
systemctl enable --now docker

cat << 'EOF' > /etc/systemd/system/cardboarddex-firewall.service
[Unit]
Description=Reject outbound IPv4 TCP forwarding with RST on IPv6-only host
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'iptables -C FORWARD -p tcp ! -d 172.16.0.0/12 -j REJECT --reject-with tcp-reset 2>/dev/null || iptables -I FORWARD 1 -p tcp ! -d 172.16.0.0/12 -j REJECT --reject-with tcp-reset'

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now cardboarddex-firewall.service

