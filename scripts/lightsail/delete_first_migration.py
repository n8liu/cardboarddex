#!/usr/bin/env python3
"""Guarded AWS phase of delete-first recovery; preview unless --apply is given.

Requires a stopped source, an available manual snapshot, a restore receipt, and
reviewed launch data. Host quiescing and application validation are separate gates.
State contains no credentials. Ambiguous API failures require inspection, not retry.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import time

import boto3
from botocore.exceptions import ClientError

ACCOUNT = '349558247779'
REGION = 'us-west-2'
SOURCE = 'cardboarddex-ipv6'
TARGET = 'cardboarddex-ipv6-1gb'
FALLBACK = 'cardboarddex-recovered'
BUCKET = f'cardboarddex-backups-{ACCOUNT}-{REGION}'


def launch_data(bootstrap):
    # Lightsail prepends a /bin/sh initialization script, so a supplied shebang
    # alone does not select bash. Explicitly launch it without echoing secrets.
    delimiter = 'CARDBOARDDEX_BOOTSTRAP_EOF'
    if delimiter in bootstrap:
        raise ValueError('Bootstrap contains reserved heredoc delimiter')
    return f"exec /bin/bash <<'{delimiter}'\n{bootstrap}\n{delimiter}\n"


def save(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def verify_gate(source, snapshot, receipt, now):
    if source['name'] != SOURCE or source['bundleId'] != 'nano_3_0':
        raise RuntimeError('Unexpected source identity or bundle')
    if source['state']['name'] != 'stopped':
        raise RuntimeError('Source must be stopped before deletion')
    if (snapshot['state'] != 'available' or snapshot.get('fromInstanceName') != SOURCE
            or snapshot.get('fromInstanceArn') != source['arn'] or snapshot.get('sizeInGb') != 20):
        raise RuntimeError('Snapshot unavailable or not from the exact source and disk')
    verified = datetime.fromisoformat(receipt['verified_at'])
    if not 0 <= (now - verified).total_seconds() <= 7200:
        raise RuntimeError('Restore receipt must be less than two hours old')
    if (receipt.get('bucket') != BUCKET or receipt.get('postgres_restored') is not True
            or receipt.get('redis_restored') is not True):
        raise RuntimeError('Both off-server restores must pass in the expected bucket')
    if snapshot['createdAt'] < verified:
        raise RuntimeError('Snapshot must follow verification of final quiesced backups')


def find_instance(client, name):
    try:
        return client.get_instance(instanceName=name)['instance']
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'NotFoundException':
            raise
        return None


def wait_operation(client, operation_id, sleep=time.sleep):
    for _ in range(60):
        op = client.get_operation(operationId=operation_id)['operation']
        if op['status'] == 'Failed':
            raise RuntimeError(f"AWS operation failed: {op.get('errorCode')}: {op.get('errorDetails')}")
        if op['status'] in ('Succeeded', 'Completed'):
            return
        sleep(10)
    raise TimeoutError('AWS operation unresolved; inspect recorded operation before resuming')


def create(client, state, path, bootstrap, fallback=False):
    name = FALLBACK if fallback else TARGET
    bundle = 'nano_3_0' if fallback else 'micro_ipv6_3_0'
    for candidate in (SOURCE, TARGET, FALLBACK):
        if find_instance(client, candidate):
            raise RuntimeError(f'Instance {candidate} exists; inspect before creating another')
    state['phase'] = 'fallback_requested' if fallback else 'target_requested'
    save(path, state)  # Persist intent BEFORE an API request that may time out.
    try:
        response = client.create_instances_from_snapshot(
            instanceNames=[name], instanceSnapshotName=state['snapshot_name'],
            availabilityZone='us-west-2a', bundleId=bundle,
            ipAddressType='dualstack' if fallback else 'ipv6',
            keyPairName='LightsailDefaultKeyPair', userData=launch_data(bootstrap),
        )
    except ClientError as exc:
        error = exc.response['Error']
        logging.error('CreateInstancesFromSnapshot failed: %s: %s', error['Code'], error['Message'])
        if not fallback and error['Code'] == 'InvalidInputException':
            state['phase'] = 'target_rejected'
            state['error'] = error
            save(path, state)
        raise
    state['operations'] = [op['id'] for op in response['operations']]
    if not state['operations']:
        raise RuntimeError('AWS returned no operation IDs; inspect inventory before resuming')
    save(path, state)
    for operation in state['operations']:
        wait_operation(client, operation)
    state['phase'] = 'fallback_created' if fallback else 'target_created'
    save(path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--bootstrap', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--fallback', action='store_true')
    args = parser.parse_args()
    session = boto3.Session(region_name=REGION)
    if session.client('sts').get_caller_identity()['Account'] != ACCOUNT:
        raise RuntimeError('Unexpected AWS account')
    client = session.client('lightsail')
    receipt = json.loads(args.receipt.read_text())
    snapshot = client.get_instance_snapshot(instanceSnapshotName=args.snapshot)['instanceSnapshot']
    if snapshot['state'] != 'available':
        raise RuntimeError('Recovery snapshot is not available')
    bootstrap = args.bootstrap.read_text()
    if not bootstrap.startswith('#!/bin/bash\n'):
        raise RuntimeError('Expected reviewed bash launch data')
    if args.state.exists():
        state = json.loads(args.state.read_text())
        if (state['snapshot_arn'] != snapshot['arn'] or state['snapshot_name'] != args.snapshot
                or state['receipt_sha256'] != hashlib.sha256(args.receipt.read_bytes()).hexdigest()
                or state['bootstrap_sha256'] != hashlib.sha256(bootstrap.encode()).hexdigest()):
            raise RuntimeError('Recovery artifacts differ from checkpoint')
    else:
        source = find_instance(client, SOURCE)
        if not source:
            raise RuntimeError('Missing source and no checkpoint; manual recovery inspection required')
        verify_gate(source, snapshot, receipt, datetime.now(timezone.utc))
        state = {'phase': 'verified', 'source_arn': source['arn'],
                 'snapshot_name': args.snapshot, 'snapshot_arn': snapshot['arn'],
                 'receipt_sha256': hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
                 'bootstrap_sha256': hashlib.sha256(bootstrap.encode()).hexdigest()}
    print(json.dumps({'phase': state['phase'], 'snapshot': args.snapshot,
                      'apply': args.apply, 'fallback': args.fallback}))
    if not args.apply:
        return
    if args.fallback:
        if state['phase'] != 'target_rejected':
            raise RuntimeError('Automatic fallback requires explicit target rejection; inspect other failures manually')
        create(client, state, args.state, bootstrap, fallback=True)
        return
    if state['phase'] == 'verified':
        source = find_instance(client, SOURCE)
        verify_gate(source, snapshot, receipt, datetime.now(timezone.utc))
        if source['arn'] != state['source_arn']:
            raise RuntimeError('Source changed since checkpoint')
        state['phase'] = 'delete_requested'
        state['deleted_requested_at'] = datetime.now(timezone.utc).isoformat()
        save(args.state, state)
        result = client.delete_instance(instanceName=SOURCE)
        state['operations'] = [op['id'] for op in result['operations']]
        save(args.state, state)
        for operation in state['operations']:
            wait_operation(client, operation)
        if find_instance(client, SOURCE):
            raise RuntimeError('Source still present after deletion operation')
        state['phase'] = 'source_deleted'
        save(args.state, state)
    if state['phase'] != 'source_deleted':
        raise RuntimeError('Checkpoint requires manual AWS inspection before further mutation')
    create(client, state, args.state, bootstrap)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception:
        logging.exception('Delete-first migration stopped; recovery artifacts retained')
        raise SystemExit(1)
