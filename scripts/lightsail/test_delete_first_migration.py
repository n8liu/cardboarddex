import importlib.util
from datetime import datetime, timedelta, timezone
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

spec = importlib.util.spec_from_file_location('migration', Path(__file__).with_name('delete_first_migration.py'))
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def artifacts():
    now = datetime.now(timezone.utc)
    source = {'name': migration.SOURCE, 'arn': 'source-arn', 'bundleId': 'nano_3_0',
              'state': {'name': 'stopped'}}
    snapshot = {'state': 'available', 'fromInstanceName': migration.SOURCE,
                'fromInstanceArn': 'source-arn', 'sizeInGb': 20,
                'createdAt': now - timedelta(minutes=1)}
    receipt = {'bucket': migration.BUCKET, 'postgres_restored': True, 'redis_restored': True,
               'verified_at': (now - timedelta(minutes=2)).isoformat()}
    return source, snapshot, receipt, now


def test_verified_artifacts_pass(artifacts):
    migration.verify_gate(*artifacts)


@pytest.mark.parametrize('field,value', [('state', 'pending'), ('fromInstanceArn', 'wrong'), ('sizeInGb', 40)])
def test_snapshot_gate(artifacts, field, value):
    artifacts[1][field] = value
    with pytest.raises(RuntimeError):
        migration.verify_gate(*artifacts)


@pytest.mark.parametrize('field,value', [('name', 'other'), ('state', {'name': 'running'})])
def test_source_gate(artifacts, field, value):
    artifacts[0][field] = value
    with pytest.raises(RuntimeError):
        migration.verify_gate(*artifacts)


@pytest.mark.parametrize('field,value', [('postgres_restored', False), ('redis_restored', False),
                                      ('bucket', 'unknown'), ('verified_at', '2020-01-01T00:00:00+00:00')])
def test_unverified_backup_blocks_delete(artifacts, field, value):
    artifacts[2][field] = value
    with pytest.raises(RuntimeError):
        migration.verify_gate(*artifacts)


def test_old_snapshot_rejected(artifacts):
    artifacts[1]['createdAt'] = artifacts[3] - timedelta(hours=1)
    with pytest.raises(RuntimeError, match='must follow'):
        migration.verify_gate(*artifacts)


def test_creation_timeout_leaves_intent_and_does_not_retry(tmp_path):
    client = Mock()
    client.get_instance.side_effect = ClientError({'Error': {'Code': 'NotFoundException'}}, 'GetInstance')
    client.create_instances_from_snapshot.side_effect = EndpointConnectionError(endpoint_url='https://example.invalid')
    state = {'phase': 'source_deleted', 'snapshot_name': 'saved'}
    path = tmp_path / 'state.json'
    with pytest.raises(EndpointConnectionError):
        migration.create(client, state, path, '#!/bin/bash\n')
    assert json.loads(path.read_text())['phase'] == 'target_requested'
    client.create_instances_from_snapshot.assert_called_once()
    client.delete_instance.assert_not_called()


def test_explicit_rejection_checkpoint_and_fallback_bundle(tmp_path):
    client = Mock()
    client.get_instance.side_effect = ClientError({'Error': {'Code': 'NotFoundException'}}, 'GetInstance')
    client.create_instances_from_snapshot.side_effect = ClientError(
        {'Error': {'Code': 'InvalidInputException', 'Message': 'nano only'}}, 'CreateInstancesFromSnapshot')
    state = {'snapshot_name': 'saved'}
    path = tmp_path / 'state.json'
    with pytest.raises(ClientError):
        migration.create(client, state, path, '#!/bin/bash\n')
    assert json.loads(path.read_text())['phase'] == 'target_rejected'
    client.create_instances_from_snapshot.side_effect = None
    client.create_instances_from_snapshot.return_value = {'operations': [{'id': 'op'}]}
    client.get_operation.return_value = {'operation': {'status': 'Succeeded'}}
    migration.create(client, state, path, '#!/bin/bash\n', fallback=True)
    assert client.create_instances_from_snapshot.call_args.kwargs['bundleId'] == 'nano_3_0'
    assert client.create_instances_from_snapshot.call_args.kwargs['ipAddressType'] == 'dualstack'


def test_existing_target_prevents_duplicate_creation(tmp_path):
    client = Mock()
    client.get_instance.return_value = {'instance': {'name': migration.TARGET}}
    with pytest.raises(RuntimeError, match='exists'):
        migration.create(client, {}, tmp_path / 'state.json', '#!/bin/bash\n')
    client.create_instances_from_snapshot.assert_not_called()


def test_lightsail_sh_wrapper_executes_bash_bootstrap():
    script = migration.launch_data('#!/bin/bash\nset -euo pipefail\n[[ 1 == 1 ]]\necho ready')
    result = subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True)
    assert result.returncode == 0
    assert result.stdout.strip() == 'ready'


def test_bootstrap_delimiter_collision_rejected():
    with pytest.raises(ValueError, match='reserved'):
        migration.launch_data('CARDBOARDDEX_BOOTSTRAP_EOF')
