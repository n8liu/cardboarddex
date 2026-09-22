#!/usr/bin/env bash
# Deploy a previously built AMD64 release. Does not build, push latest, or migrate schemas.
set -euo pipefail
: "${LIGHTSAIL_HOST:?Configure the verified deployment hostname or IP}"
: "${KEY_PATH:?Set the deployment SSH key path}"
: "${KNOWN_HOSTS_FILE:?Set a file containing the independently verified SSH host key}"
: "${BACKEND_IMAGE:?Set the CI-built image@sha256:digest}"
: "${RELEASE_ID:?Set the release commit SHA}"
: "${LIGHTSAIL_USER:=ubuntu}"
: "${AWS_REGION:=us-west-2}"
[[ "$RELEASE_ID" =~ ^[a-f0-9]{40}$ ]] || { echo 'RELEASE_ID must be a commit SHA' >&2; exit 1; }
[[ "$BACKEND_IMAGE" =~ @sha256:[a-f0-9]{64}$ ]] || exit 1
[[ "$LIGHTSAIL_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || exit 1
# Accept bare IPv6 literals as well as IPv4 addresses and DNS hostnames.
# Validate before passing the destination to SSH; never accept SSH options here.
python3 - "$LIGHTSAIL_HOST" <<'PY'
import ipaddress
import re
import sys

host = sys.argv[1]
try:
    ipaddress.ip_address(host)
except ValueError:
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
        raise SystemExit('LIGHTSAIL_HOST must be an IP address or DNS hostname')
if '%' in host:
    raise SystemExit('Scoped IPv6 addresses are not supported for deployment')
PY
[[ "$BACKEND_IMAGE" =~ ^349558247779\.(dkr\.ecr\.us-west-2\.amazonaws\.com|dkr-ecr\.us-west-2\.on\.aws)/cardboarddex-backend@sha256:[a-f0-9]{64}$ ]] || exit 1
repo=$(cd "$(dirname "$0")/.." && pwd)
remote="${LIGHTSAIL_USER}@${LIGHTSAIL_HOST}"

if ! ssh-keygen -y -f "$KEY_PATH" > /dev/null 2>&1; then
  echo "ERROR: KEY_PATH ($KEY_PATH) does not contain a valid private key format." >&2
  exit 1
fi

ssh_opts=(
  -i "$KEY_PATH"
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE"
  -o PubkeyAcceptedKeyTypes=+ssh-rsa
  -o HostKeyAlgorithms=+ssh-rsa
  -o ConnectTimeout=75
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=3
)

if [[ -n "${LIGHTSAIL_SSM_TARGET:-}" ]]; then
  [[ "$LIGHTSAIL_SSM_TARGET" =~ ^mi-[a-f0-9]{17}$ ]] || { echo 'Invalid SSM managed node ID' >&2; exit 1; }
  [[ "$AWS_REGION" == us-west-2 ]] || exit 1
fi
ssh_log=$(mktemp)
# macOS limits Unix socket paths to 104 bytes; TMPDIR can already be longer.
control_dir=$(mktemp -d /tmp/cardboarddex-ssh.XXXXXXXX)
cleanup() {
  if [[ -n "${LIGHTSAIL_SSM_TARGET:-}" ]]; then
    ssh "${ssh_opts[@]}" -O exit "$remote" >/dev/null 2>&1 || true
  fi
  rm -f "$ssh_log"
  rm -rf "$control_dir"
}
trap cleanup EXIT
if [[ -n "${LIGHTSAIL_SSM_TARGET:-}" ]]; then
  # One authenticated SSM session carries every SSH command in this deploy.
  # Strict host-key checking and SSH public-key authentication still apply.
  ssh_opts+=(
    -o "ProxyCommand=aws ssm start-session --target $LIGHTSAIL_SSM_TARGET --document-name AWS-StartSSHSession --parameters portNumber=%p --region $AWS_REGION"
    -o ControlMaster=auto
    -o ControlPersist=60
    -o "ControlPath=$control_dir/connection"
  )
fi
for attempt in 1 2 3; do
  echo "Testing SSH session to ${remote} (attempt $attempt/3)..."
  # Bound the entire probe, including session setup after authentication.
  # ConnectTimeout alone only bounds connection establishment and handshake.
  if LC_ALL=C python3 - "${ssh_opts[@]}" "$remote" true 2> "$ssh_log" <<'PY'
import subprocess
import sys

try:
    result = subprocess.run(
        ['ssh', '-v', *sys.argv[1:]], stdin=subprocess.DEVNULL, timeout=75,
    )
except subprocess.TimeoutExpired as exc:
    print(f'SSH session probe timed out after {exc.timeout} seconds', file=sys.stderr)
    raise SystemExit(124)
raise SystemExit(result.returncode)
PY
  then
    break
  else
    ssh_status=$?
  fi
  cat "$ssh_log" >&2
  if grep -q '^Authenticated to ' "$ssh_log"; then
    echo "ERROR: SSH authentication succeeded, but the remote session probe failed (exit $ssh_status)." >&2
    echo 'Inspect server memory/swap, disk usage, and SSH/PAM logs; a network interruption is also possible.' >&2
    if (( attempt < 3 )) && [[ "$ssh_status" == 255 || "$ssh_status" == 124 ]]; then
      echo 'Retrying the read-only SSH probe in 5 seconds...' >&2
      sleep 5
      continue
    fi
  elif grep -Eq 'REMOTE HOST IDENTIFICATION HAS CHANGED|Host key verification failed' "$ssh_log"; then
    echo 'ERROR: SSH host verification failed. Check LIGHTSAIL_KNOWN_HOSTS against the independently verified server host key.' >&2
  elif grep -Eq 'Permission denied|Load key .*:' "$ssh_log"; then
    echo 'ERROR: SSH authentication failed. Check LIGHTSAIL_SSH_KEY and the deployment user authorized_keys.' >&2
  else
    echo 'ERROR: SSH did not complete authentication. Check the server address, port 22 reachability, and SSH logs above.' >&2
  fi
  exit 1
done
rm -f "$ssh_log"
echo "SSH connection verified successfully."

release="/opt/cardboarddex/releases/$RELEASE_ID"
registry=${BACKEND_IMAGE%%/*}
aws ecr get-login-password --region "$AWS_REGION" | ssh "${ssh_opts[@]}" "$remote" "docker login --username AWS --password-stdin '$registry'"
# The same commit can be retried, but its image/configuration cannot be replaced.
fingerprint=$(python3 - "$repo" "$BACKEND_IMAGE" <<'PY'
import hashlib
from pathlib import Path
import sys
root=Path(sys.argv[1])
files=[root/'docker-compose.prod.yml']
for directory in ('scripts/lightsail','deploy/lightsail'):
    files.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
h=hashlib.sha256(sys.argv[2].encode())
for path in sorted(files):
    h.update(str(path.relative_to(root)).encode()+b'\0'+path.read_bytes()+b'\0')
print(h.hexdigest())
PY
)
stage=$(ssh "${ssh_opts[@]}" "$remote" "mktemp -d '/opt/cardboarddex/releases/.stage-$RELEASE_ID.XXXXXX'")
[[ "$stage" == /opt/cardboarddex/releases/.stage-"$RELEASE_ID".* ]] || exit 1
tar --exclude='__pycache__' --exclude='*.pyc' -C "$repo" -czf - docker-compose.prod.yml scripts/lightsail deploy/lightsail | ssh "${ssh_opts[@]}" "$remote" "tar -xzf - -C '$stage'"
printf '%s\n' "$BACKEND_IMAGE" | ssh "${ssh_opts[@]}" "$remote" "cat > '$stage/image.txt'"
printf '%s\n' "$fingerprint" | ssh "${ssh_opts[@]}" "$remote" "cat > '$stage/source.sha256'"
ssh "${ssh_opts[@]}" "$remote" "if [ -d '$release' ]; then cmp '$stage/source.sha256' '$release/source.sha256' && rm -rf '$stage'; else mv -T '$stage' '$release'; fi"
ssh "${ssh_opts[@]}" "$remote" "bash '$release/scripts/lightsail/release.sh' '$release'"
