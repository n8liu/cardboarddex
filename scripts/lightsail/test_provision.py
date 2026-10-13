"""Provisioning must preserve the current server when migration cannot proceed."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError


spec = importlib.util.spec_from_file_location('provision', Path(__file__).with_name('provision.py'))
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


@pytest.fixture
def lightsail():
    lightsail = Mock()
    lightsail.get_bundles.return_value = {'bundles': [{
        'bundleId': provision.BUNDLE, 'isActive': True, 'price': 7,
        'ramSizeInGb': 1, 'diskSizeInGb': 40, 'publicIpv4AddressCount': 1,
    }]}
    lightsail.get_instance.return_value = {'instance': {
        'bundleId': provision.BUNDLE, 'ipAddressType': 'dualstack',
        'publicIpAddress': '192.0.2.1', 'ipv6Addresses': ['2001:db8::1'], 'state': {'name': 'running'},
        'hardware': {'ramSizeInGb': 1, 'cpuCount': 2,
                     'disks': [{'isSystemDisk': True, 'sizeInGb': 40}]},
    }}
    lightsail.get_operation.return_value = {'operation': {'id': 'op-1', 'status': 'Succeeded'}}
    return lightsail


def test_creates_one_gigabyte_dualstack_destination(lightsail):
    lightsail.get_instances.return_value = {'instances': [{'name': 'cardboarddex-server'}]}
    provision.provision_instance(lightsail)
    args = lightsail.create_instances.call_args.kwargs
    assert args['bundleId'] == 'micro_3_0'
    assert args['ipAddressType'] == 'dualstack'
    assert args['instanceNames'] == ['cardboarddex-1gb']
    lightsail.delete_instance.assert_not_called()
    lightsail.allocate_static_ip.assert_not_called()


@pytest.mark.parametrize('message', [
    'maximum limit of Lightsail Instances : 1',
    'your account can only create an instance using the smallest Lightsail plan size (nano)',
])
def test_quota_rejection_never_deletes_the_source(lightsail, message):
    lightsail.get_instances.return_value = {'instances': [{'name': 'cardboarddex-server'}]}
    lightsail.create_instances.side_effect = ClientError(
        {'Error': {'Code': 'InvalidInputException', 'Message': message}},
        'CreateInstances',
    )
    with pytest.raises(ClientError) as error:
        provision.provision_instance(lightsail)
    assert error.value.response['Error']['Message'] == message
    lightsail.delete_instance.assert_not_called()
    lightsail.stop_instance.assert_not_called()


@pytest.mark.parametrize('bundle', ['micro_3_0', 'nano_3_0'])
def test_existing_destination_is_validated_without_replacement(lightsail, bundle):
    lightsail.get_instances.return_value = {'instances': [{
        'name': provision.INSTANCE, 'bundleId': bundle, 'ipAddressType': 'dualstack',
    }]}
    if bundle == 'micro_3_0':
        provision.provision_instance(lightsail)
    else:
        with pytest.raises(RuntimeError, match='does not match'):
            provision.provision_instance(lightsail)
    lightsail.create_instances.assert_not_called()
    lightsail.delete_instance.assert_not_called()


@pytest.mark.parametrize('source', sorted(provision.PROTECTED_SOURCES))
def test_refuses_production_name(lightsail, source):
    with pytest.raises(RuntimeError, match='production source'):
        provision.provision_instance(lightsail, source)
    lightsail.create_instances.assert_not_called()


def test_custom_destination_and_paginated_inventory(lightsail):
    lightsail.get_instances.side_effect = [
        {'instances': [{'name': provision.SOURCE}], 'nextPageToken': 'page2'},
        {'instances': [{'name': 'custom', 'bundleId': provision.BUNDLE, 'ipAddressType': 'dualstack'}]},
    ]
    provision.provision_instance(lightsail, 'custom')
    lightsail.get_instances.assert_called_with(pageToken='page2')
    lightsail.create_instances.assert_not_called()


@pytest.mark.parametrize('field,value', [
    ('isActive', False), ('price', 5), ('ramSizeInGb', 0.5),
    ('diskSizeInGb', 20), ('publicIpv4AddressCount', 0),
])
def test_rejects_unexpected_bundle(lightsail, field, value):
    lightsail.get_bundles.return_value['bundles'][0][field] = value
    with pytest.raises(RuntimeError, match='unavailable'):
        provision.provision_instance(lightsail)
    lightsail.create_instances.assert_not_called()


def test_rejects_existing_ipv6_only_destination(lightsail):
    lightsail.get_instances.return_value = {'instances': [{
        'name': provision.INSTANCE, 'bundleId': provision.BUNDLE, 'ipAddressType': 'ipv6',
    }]}
    with pytest.raises(RuntimeError, match='does not match'):
        provision.provision_instance(lightsail)
    lightsail.create_instances.assert_not_called()


@pytest.mark.parametrize('reject', [False, True])
def test_instance_only_never_touches_backup_resources(lightsail, monkeypatch, reject):
    session = Mock()
    sts = Mock()
    sts.get_caller_identity.return_value = {'Account': provision.ACCOUNT}
    session.client.side_effect = {'sts': sts, 'lightsail': lightsail}.__getitem__
    monkeypatch.setattr(provision.boto3, 'Session', Mock(return_value=session))
    monkeypatch.setattr('sys.argv', ['provision.py', '--apply', '--instance-only', '--instance-name', 'custom'])
    lightsail.get_instances.return_value = {'instances': [{'name': provision.SOURCE}]}
    lightsail.create_instances.return_value = {'operations': [{'id': 'op-1'}]}
    if reject:
        lightsail.create_instances.side_effect = ClientError(
            {'Error': {'Code': 'InvalidInputException', 'Message': 'nano only'}}, 'CreateInstances')
        with pytest.raises(ClientError):
            provision.main()
    else:
        provision.main()
        assert lightsail.create_instances.call_args.kwargs['instanceNames'] == ['custom']
    assert {call.args[0] for call in session.client.call_args_list} == {'sts', 'lightsail'}


def test_waits_for_operation_before_reading_hardware(lightsail):
    lightsail.get_operation.side_effect = [
        {'operation': {'id': 'op-1', 'status': 'Started'}},
        {'operation': {'id': 'op-1', 'status': 'Succeeded'}},
    ]
    sleep = Mock()
    result = provision.wait_for_instance(lightsail, 'custom', {'operations': [{'id': 'op-1'}]}, sleep=sleep)
    assert result['state'] == 'running'
    sleep.assert_called_once_with(10)
    lightsail.get_instance.assert_called_once_with(instanceName='custom')


def test_failed_operation_preserves_aws_error(lightsail):
    lightsail.get_operation.return_value = {'operation': {
        'id': 'op-1', 'status': 'Failed', 'errorCode': 'Capacity', 'errorDetails': 'Unavailable in zone',
    }}
    with pytest.raises(RuntimeError, match='Capacity: Unavailable in zone'):
        provision.wait_for_instance(lightsail, 'custom', {'operations': [{'id': 'op-1'}]})
    lightsail.get_instance.assert_not_called()


@pytest.mark.parametrize('field,value', [
    ('bundleId', 'nano_3_0'), ('ipAddressType', 'ipv6'),
    ('publicIpAddress', None), ('ipv6Addresses', []),
    ('hardware', {'ramSizeInGb': 0.5, 'cpuCount': 2, 'disks': []}),
    ('hardware', {'ramSizeInGb': 1, 'cpuCount': 2,
                  'disks': [{'isSystemDisk': True, 'sizeInGb': 20}]}),
])
def test_readiness_rejects_wrong_actual_configuration(lightsail, field, value):
    lightsail.get_instance.return_value['instance'][field] = value
    with pytest.raises(RuntimeError, match='hardware/network'):
        provision.wait_for_instance(lightsail, 'custom', {'existing': True})


def test_readiness_times_out_without_mutation(lightsail):
    lightsail.get_instance.return_value['instance']['state']['name'] = 'pending'
    sleep = Mock()
    with pytest.raises(TimeoutError):
        provision.wait_for_instance(lightsail, 'custom', {'existing': True}, attempts=2, sleep=sleep)
    sleep.assert_called_once_with(10)
    lightsail.stop_instance.assert_not_called()
    lightsail.delete_instance.assert_not_called()


def test_empty_operation_response_cannot_report_success(lightsail):
    with pytest.raises(RuntimeError, match='no operation'):
        provision.wait_for_instance(lightsail, 'custom', {'operations': []})


def test_failed_readiness_prevents_backup_and_iam_changes(lightsail, monkeypatch):
    session = Mock()
    sts = Mock()
    sts.get_caller_identity.return_value = {'Account': provision.ACCOUNT}
    session.client.side_effect = {'sts': sts, 'lightsail': lightsail}.__getitem__
    monkeypatch.setattr(provision.boto3, 'Session', Mock(return_value=session))
    monkeypatch.setattr('sys.argv', ['provision.py', '--apply'])
    lightsail.get_instances.return_value = {'instances': []}
    lightsail.create_instances.return_value = {'operations': [{'id': 'op-1'}]}
    lightsail.get_operation.return_value = {'operation': {
        'id': 'op-1', 'status': 'Failed', 'errorCode': 'Capacity', 'errorDetails': 'Unavailable',
    }}
    with pytest.raises(RuntimeError, match='Capacity'):
        provision.main()
    assert {call.args[0] for call in session.client.call_args_list} == {'sts', 'lightsail'}
