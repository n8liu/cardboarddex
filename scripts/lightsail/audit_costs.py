#!/usr/bin/env python3
"""Read-only inventory and month-to-date costs; never deletes resources."""
from datetime import datetime, timezone
import json
import logging
import boto3
from botocore.exceptions import ClientError


def audit():
    session = boto3.Session(region_name='us-west-2')
    now = datetime.now(timezone.utc)
    report = {'checked_at': now.isoformat(), 'regions': {}}
    regions = session.client('ec2').describe_regions()['Regions']
    for region in regions:
        name = region['RegionName']
        ec2 = session.client('ec2', region_name=name)
        rds = session.client('rds', region_name=name)
        entry = {}
        entry['elastic_ips'] = [{k: a.get(k) for k in ('AllocationId','AssociationId','PublicIp')} for a in ec2.describe_addresses()['Addresses']]
        entry['nat_gateways'] = [{k: a.get(k) for k in ('NatGatewayId','State')} for a in ec2.describe_nat_gateways()['NatGateways'] if a['State'] != 'deleted']
        entry['unattached_volumes'] = [{k:a.get(k) for k in ('VolumeId','Size')} for a in ec2.describe_volumes(Filters=[{'Name':'status','Values':['available']}])['Volumes']]
        entry['load_balancers'] = [a['LoadBalancerName'] for a in session.client('elbv2', region_name=name).describe_load_balancers()['LoadBalancers']]
        entry['rds_instances'] = [a['DBInstanceIdentifier'] for a in rds.describe_db_instances()['DBInstances']]
        entry['rds_manual_snapshots'] = [a['DBSnapshotIdentifier'] for a in rds.describe_db_snapshots(SnapshotType='manual')['DBSnapshots']]
        if any(entry.values()):
            report['regions'][name] = entry
    try:
        if now.day > 1:
            report['month_to_date'] = session.client('ce', region_name='us-east-1').get_cost_and_usage(
                TimePeriod={'Start':now.strftime('%Y-%m-01'),'End':now.strftime('%Y-%m-%d')}, Granularity='MONTHLY',
                Metrics=['UnblendedCost'], GroupBy=[{'Type':'DIMENSION','Key':'SERVICE'}])['ResultsByTime']
    except ClientError as exc:
        logging.error('Cost Explorer unavailable: %s', exc)
        report['billing_error'] = str(exc)
    print(json.dumps(report, default=str, indent=2))


if __name__ == '__main__':
    try:
        audit()
    except Exception:
        logging.exception('Cost audit failed')
        raise SystemExit(1)
