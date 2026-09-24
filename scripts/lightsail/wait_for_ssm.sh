#!/usr/bin/env bash
# An Online heartbeat is a prerequisite; the deployment SSH probe verifies the session.
set -euo pipefail
: "${1:?SSM managed node ID required}"
target=$1
region=${AWS_REGION:-us-west-2}
[[ "$target" =~ ^mi-[a-f0-9]{17}$ ]] || { echo 'Invalid SSM managed node ID' >&2; exit 1; }
[[ "$region" == us-west-2 ]] || { echo 'Unexpected deployment region' >&2; exit 1; }

for attempt in {1..30}; do
  # Keep AWS errors visible, including permission failures, instead of treating
  # every failed API request as an offline node.
  if ! status=$(AWS_MAX_ATTEMPTS=1 aws ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$target" \
    --query 'InstanceInformationList[0].PingStatus' --output text \
    --region "$region" --cli-connect-timeout 5 --cli-read-timeout 10); then
    echo "ERROR: Could not query SSM target $target; deployment stopped." >&2
    exit 1
  fi
  if [[ "$status" == Online ]]; then
    echo "SSM target $target is Online."
    exit 0
  fi
  echo "SSM target $target status is '$status' (attempt $attempt/30)."
  if (( attempt < 30 )); then
    sleep 5
  fi
done

echo "ERROR: SSM target $target did not become Online; deployment stopped before SSH. Restore host/SSM connectivity before retrying." >&2
exit 1
