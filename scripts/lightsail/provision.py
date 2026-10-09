#!/usr/bin/env python3
"""Provision the reviewed $5 Lightsail instance and private backup storage. Preview by default."""
import argparse
import json
import logging
import os
import time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

ACCOUNT = '349558247779'
REGION = 'us-west-2'
BUCKET = f'cardboarddex-backups-{ACCOUNT}-{REGION}'
INSTANCE = 'cardboarddex-ipv6-1gb'
SOURCE = 'cardboarddex-ipv6'
BUNDLE = 'micro_ipv6_3_0'
USER = 'cardboarddex-backup-upload'
ROLE = 'github-actions-cardboarddex-backup-read'


def only_missing(error, codes):
    if error.response['Error']['Code'] not in codes:
        raise error


def list_resources(method, key):
    response = method()
    yield from response[key]
    while response.get('nextPageToken'):
        response = method(pageToken=response['nextPageToken'])
        yield from response[key]


def validate_destination(lightsail, instance_name):
    if instance_name == SOURCE:
        raise RuntimeError('Destination must differ from the production source')
    bundle = next((b for b in list_resources(lightsail.get_bundles, 'bundles')
                   if b['bundleId'] == BUNDLE), None)
    if not bundle or not bundle.get('isActive') or any(
        bundle.get(key) != value for key, value in
        [('ramSizeInGb', 1), ('diskSizeInGb', 40), ('price', 5),
         ('publicIpv4AddressCount', 0)]
    ):
        raise RuntimeError('Requested active $5 / 1 GB / 40 GB bundle is unavailable')
    existing = next((i for i in list_resources(lightsail.get_instances, 'instances')
                     if i['name'] == instance_name), None)
    if existing:
        if existing['bundleId'] != BUNDLE or existing['ipAddressType'] != 'ipv6':
            raise RuntimeError('Existing destination does not match the $5 IPv6-only plan; refusing to replace it')
    return existing


def provision_instance(lightsail, instance_name=INSTANCE):
    existing = validate_destination(lightsail, instance_name)
    if existing:
        return {'instance': instance_name, 'existing': True}
    # A quota rejection must leave the source instance intact.
    return lightsail.create_instances(
        instanceNames=[instance_name], availabilityZone='us-west-2a',
        blueprintId='ubuntu_24_04', bundleId=BUNDLE, ipAddressType='ipv6',
        keyPairName='LightsailDefaultKeyPair',
        tags=[{'key': 'Project', 'value': 'cardboarddex'}, {'key': 'Purpose', 'value': 'production'}],
    )


def wait_for_instance(lightsail, instance_name, result, attempts=60, sleep=time.sleep):
    """Verify async creation and actual hardware before allowing follow-on changes."""
    if instance_name == SOURCE:
        raise RuntimeError('Refusing readiness checks against production source')
    operations = result.get('operations', [])
    if not result.get('existing') and not operations:
        raise RuntimeError('CreateInstances returned no operation; readiness is unverified')
    for attempt in range(attempts):
        complete = True
        for original in operations:
            operation = lightsail.get_operation(operationId=original['id'])['operation']
            if operation['status'] == 'Failed':
                raise RuntimeError(f"Lightsail operation {operation['id']} failed: "
                                   f"{operation.get('errorCode')}: {operation.get('errorDetails')}")
            complete = complete and operation['status'] in ('Succeeded', 'Completed')
        if complete:
            instance = lightsail.get_instance(instanceName=instance_name)['instance']
            if instance['state']['name'] == 'running':
                hardware = instance.get('hardware', {})
                disks = hardware.get('disks', [])
                if (instance.get('bundleId') != BUNDLE
                        or instance.get('ipAddressType') != 'ipv6'
                        or instance.get('publicIpAddress')
                        or not instance.get('ipv6Addresses')
                        or hardware.get('ramSizeInGb') != 1
                        or hardware.get('cpuCount') != 2
                        or not any(d.get('isSystemDisk') and d.get('sizeInGb') == 40 for d in disks)):
                    raise RuntimeError('Running destination hardware/network does not match reviewed plan')
                return {'instance': instance_name, 'state': 'running', 'bundle': BUNDLE,
                        'network': 'ipv6', 'ram_gb': 1, 'disk_gb': 40}
        logging.info('Waiting for replacement readiness (%s/%s)', attempt + 1, attempts)
        if attempt + 1 < attempts:
            sleep(10)
    raise TimeoutError('Replacement readiness timed out; inspect AWS before retrying; source unchanged')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--instance-name', default=INSTANCE)
    parser.add_argument('--instance-only', action='store_true',
                        help='Create only the replacement; leave backup storage and IAM unchanged')
    parser.add_argument('--state-dir', default='.system_generated/lightsail')
    args = parser.parse_args()
    session = boto3.Session(region_name=REGION)
    if session.client('sts').get_caller_identity()['Account'] != ACCOUNT:
        raise RuntimeError('Refusing unexpected AWS account')
    lightsail = session.client('lightsail')
    validate_destination(lightsail, args.instance_name)
    print(json.dumps({'instance': args.instance_name, 'bundle': BUNDLE, 'monthly_usd': 5,
                      'ram_gb': 1, 'network': 'ipv6',
                      'backup_bucket': BUCKET, 'region': REGION, 'apply': args.apply,
                      'instance_only': args.instance_only,
                      'eligibility': 'Catalog validated; account restrictions require CreateInstances acceptance'}))
    if not args.apply:
        return
    result = provision_instance(lightsail, args.instance_name)
    print(json.dumps(result, default=str))
    print(json.dumps(wait_for_instance(lightsail, args.instance_name, result)))
    if args.instance_only:
        print('Replacement running with verified hardware/network. Management and application checks remain required.')
        return
    os.umask(0o077)
    state = Path(args.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    s3, iam = (session.client(name) for name in ('s3', 'iam'))
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError as exc:
        only_missing(exc, ('404', 'NoSuchBucket'))
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={'LocationConstraint': REGION})
    s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={k: True for k in
        ('BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets')})
    s3.put_bucket_encryption(Bucket=BUCKET, ServerSideEncryptionConfiguration={
        'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps({'Version': '2012-10-17', 'Statement': [{
        'Effect':'Deny','Principal':'*','Action':'s3:*','Resource':[f'arn:aws:s3:::{BUCKET}',f'arn:aws:s3:::{BUCKET}/*'],
        'Condition':{'Bool':{'aws:SecureTransport':'false'}}}]}))
    policy_path = Path(__file__).resolve().parents[2] / 'deploy/lightsail/backup-lifecycle.json'
    s3.put_bucket_lifecycle_configuration(Bucket=BUCKET, LifecycleConfiguration=json.loads(policy_path.read_text()))
    try:
        iam.get_user(UserName=USER)
    except ClientError as exc:
        only_missing(exc, ('NoSuchEntity',))
        iam.create_user(UserName=USER)
    iam.put_user_policy(UserName=USER, PolicyName='UploadOnly', PolicyDocument=json.dumps({
        'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':['s3:PutObject'],
        'Resource':[f'arn:aws:s3:::{BUCKET}/six-hourly/*',f'arn:aws:s3:::{BUCKET}/weekly/*']}]}))
    secret_file = state / 'backup.env'
    if not secret_file.exists():
        if iam.list_access_keys(UserName=USER)['AccessKeyMetadata']:
            raise RuntimeError('Backup user has an existing key; recover its secret instead of creating another')
        key = iam.create_access_key(UserName=USER)['AccessKey']
        secret_file.write_text(f'BACKUP_BUCKET={BUCKET}\nAWS_DEFAULT_REGION={REGION}\nAWS_ACCESS_KEY_ID={key["AccessKeyId"]}\nAWS_SECRET_ACCESS_KEY={key["SecretAccessKey"]}\n')
        secret_file.chmod(0o600)
    trust = {'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{
        'Federated':f'arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com'},
        'Action':'sts:AssumeRoleWithWebIdentity','Condition':{'StringEquals':{
        'token.actions.githubusercontent.com:aud':'sts.amazonaws.com',
        'token.actions.githubusercontent.com:sub':'repo:n8liu/cardboarddex:ref:refs/heads/main'}}}]}
    try:
        iam.get_role(RoleName=ROLE)
    except ClientError as exc:
        only_missing(exc, ('NoSuchEntity',))
        iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust))
    iam.put_role_policy(RoleName=ROLE, PolicyName='ReadBackups', PolicyDocument=json.dumps({
        'Version':'2012-10-17','Statement':[
        {'Effect':'Allow','Action':'s3:ListBucket','Resource':f'arn:aws:s3:::{BUCKET}'},
        {'Effect':'Allow','Action':'s3:GetObject','Resource':f'arn:aws:s3:::{BUCKET}/*'}]}))
    (state / 'resources.json').write_text(json.dumps({'instance': args.instance_name, 'bucket': BUCKET, 'bundle': BUNDLE, 'network': 'ipv6'}))
    print('Replacement running and backup resources configured. Management and application checks remain required.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception:
        logging.exception('Lightsail provisioning failed')
        raise SystemExit(1)
