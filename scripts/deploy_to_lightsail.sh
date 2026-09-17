#!/usr/bin/env bash
# Deploy a previously built AMD64 release. Does not build, push latest, or migrate schemas.
set -euo pipefail
: "${LIGHTSAIL_HOST:?Configure the attached static IP}"
: "${KEY_PATH:?Set the deployment SSH key path}"
: "${KNOWN_HOSTS_FILE:?Set a file containing the independently verified SSH host key}"
: "${BACKEND_IMAGE:?Set the CI-built image@sha256:digest}"
: "${RELEASE_ID:?Set the release commit SHA}"
: "${LIGHTSAIL_USER:=ubuntu}"
: "${AWS_REGION:=us-west-2}"
[[ "$RELEASE_ID" =~ ^[a-f0-9]{40}$ ]] || { echo 'RELEASE_ID must be a commit SHA' >&2; exit 1; }
[[ "$BACKEND_IMAGE" =~ @sha256:[a-f0-9]{64}$ ]] || exit 1
[[ "$LIGHTSAIL_HOST" =~ ^[a-zA-Z0-9.-]+$ && "$LIGHTSAIL_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || exit 1
[[ "$BACKEND_IMAGE" =~ ^349558247779\.dkr\.ecr\.us-west-2\.amazonaws\.com/cardboarddex-backend@sha256:[a-f0-9]{64}$ ]] || exit 1
repo=$(cd "$(dirname "$0")/.." && pwd)
remote="${LIGHTSAIL_USER}@${LIGHTSAIL_HOST}"
ssh_opts=(-i "$KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE")
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
