#!/usr/bin/env bash
# Used only by the trusted main-branch image workflow. Never logs credentials.
set -euo pipefail
: "${LIGHTSAIL_HOST:?}" "${LIGHTSAIL_SSM_TARGET:?}" "${KEY_PATH:?}" "${KNOWN_HOSTS_FILE:?}"
[[ "$LIGHTSAIL_HOST" =~ ^[a-zA-Z0-9.-]+$ ]]
[[ "$LIGHTSAIL_SSM_TARGET" =~ ^mi-[a-f0-9]{17}$ ]]
ssh_args=(-i "$KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE" -o ConnectTimeout=60
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3
  -o "ProxyCommand=aws ssm start-session --region us-west-2 --target $LIGHTSAIL_SSM_TARGET --document-name AWS-StartSSHSession --parameters portNumber=%p --reason image-sync")
remote="ubuntu@$LIGHTSAIL_HOST"
case "${1:-}" in
  export)
    # Read only existing backend state; export closes before runner transfers start.
    ssh "${ssh_args[@]}" "$remote" 'docker exec app-backend-1 python -m jobs.export_image_catalog'
    ;;
  publish)
    # Same lock as deployments; stdin contains JSON only, never shell input.
    ssh "${ssh_args[@]}" "$remote" 'cat > /opt/cardboarddex/publish_image_manifest.py.tmp && mv /opt/cardboarddex/publish_image_manifest.py.tmp /opt/cardboarddex/publish_image_manifest.py' < backend/jobs/publish_image_manifest.py
    ssh "${ssh_args[@]}" "$remote" 'flock -w 120 /opt/cardboarddex/deploy.lock python3 /opt/cardboarddex/publish_image_manifest.py /opt/cardboarddex/images' < manifest.json
    ;;
  *) echo 'Usage: remote.sh export|publish' >&2; exit 2 ;;
esac
