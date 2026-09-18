"""Provisioning must preserve the current server when migration cannot proceed."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError


spec = importlib.util.spec_from_file_location('provision', Path(__file__).with_name('provision.py'))
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


def test_creates_one_gigabyte_ipv6_destination_without_public_ipv4():
    lightsail = Mock()
    lightsail.get_instances.return_value = {'instances': [{'name': 'cardboarddex-server'}]}
    provision.provision_instance(lightsail)
    args = lightsail.create_instances.call_args.kwargs
    assert args['bundleId'] == 'micro_ipv6_3_0'
    assert args['ipAddressType'] == 'ipv6'
    assert args['instanceNames'] == ['cardboarddex-ipv6']
    lightsail.delete_instance.assert_not_called()
    lightsail.allocate_static_ip.assert_not_called()


def test_quota_rejection_never_deletes_the_source():
    lightsail = Mock()
    lightsail.get_instances.return_value = {'instances': [{'name': 'cardboarddex-server'}]}
    lightsail.create_instances.side_effect = ClientError(
        {'Error': {'Code': 'InvalidInputException', 'Message': 'maximum limit of Lightsail Instances : 1'}},
        'CreateInstances',
    )
    with pytest.raises(ClientError, match='maximum limit'):
        provision.provision_instance(lightsail)
    lightsail.delete_instance.assert_not_called()
    lightsail.stop_instance.assert_not_called()


@pytest.mark.parametrize('bundle', ['micro_ipv6_3_0', 'nano_3_0'])
def test_existing_destination_is_validated_without_replacement(bundle):
    lightsail = Mock()
    lightsail.get_instances.return_value = {'instances': [{
        'name': provision.INSTANCE, 'bundleId': bundle, 'ipAddressType': 'ipv6',
    }]}
    if bundle == 'micro_ipv6_3_0':
        provision.provision_instance(lightsail)
    else:
        with pytest.raises(RuntimeError, match='does not match'):
            provision.provision_instance(lightsail)
    lightsail.create_instances.assert_not_called()
    lightsail.delete_instance.assert_not_called()
