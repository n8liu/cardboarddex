#!/usr/bin/env python3
"""Provision the reviewed $5 Lightsail instance and private backup storage. Preview by default."""
import argparse
import json
import logging
import os
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

ACCOUNT = '349558247779'
REGION = 'us-west-2'
BUCKET = f'cardboarddex-backups-{ACCOUNT}-{REGION}'
INSTANCE = 'cardboarddex-server-v2'
USER = 'cardboarddex-backup-upload'
ROLE = 'github-actions-cardboarddex-backup-read'


def only_missing(error, codes):
    if error.response['Error']['Code'] not in codes:
        raise error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--state-dir', default='.system_generated/lightsail')
    args = parser.parse_args()
    session = boto3.Session(region_name=REGION)
    if session.client('sts').get_caller_identity()['Account'] != ACCOUNT:
        raise RuntimeError('Refusing unexpected AWS account')
    print(json.dumps({'instance': INSTANCE, 'bundle': 'nano_3_0', 'monthly_usd': 5,
                      'backup_bucket': BUCKET, 'region': REGION, 'apply': args.apply}))
    if not args.apply:
        return
    os.umask(0o077)
    state = Path(args.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    s3, iam, lightsail = (session.client(name) for name in ('s3', 'iam', 'lightsail'))
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
    instances = lightsail.get_instances()['instances']
    if not any(i['name'] == INSTANCE for i in instances):
        lightsail.create_instances(instanceNames=[INSTANCE], availabilityZone='us-west-2a',
            blueprintId='ubuntu_24_04', bundleId='nano_3_0',
            tags=[{'key':'Project','value':'cardboarddex'}, {'key':'Purpose','value':'production'}])
    addresses = lightsail.get_static_ips()['staticIps']
    if not any(a['name'] == 'cardboarddex-production' for a in addresses):
        lightsail.allocate_static_ip(staticIpName='cardboarddex-production')
    (state / 'resources.json').write_text(json.dumps({'instance': INSTANCE, 'bucket': BUCKET, 'static_ip_name':'cardboarddex-production'}))
    print('Provisioned replacement, backup bucket and identities. No old resources were changed.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception:
        logging.exception('Lightsail provisioning failed')
        raise SystemExit(1)
