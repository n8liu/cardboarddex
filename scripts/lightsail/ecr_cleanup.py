#!/usr/bin/env python3
"""Preview by default. Protect running/rollback digests and newest three releases."""
import argparse
import json
import logging
import boto3


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repository', default='cardboarddex-backend')
    p.add_argument('--region', default='us-west-2')
    p.add_argument('--protect', action='append', required=True, help='Running and previous release digest (repeat)')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    client = boto3.client('ecr', region_name=args.region)
    images = [i for page in client.get_paginator('describe_images').paginate(repositoryName=args.repository) for i in page['imageDetails']]
    images.sort(key=lambda i: i['imagePushedAt'], reverse=True)
    keep = set(args.protect)
    keep.update(i['imageDigest'] for i in [x for x in images if x.get('imageTags')][:3])
    # Resolve protected OCI indexes before considering untagged platform/attestation manifests.
    pending = list(keep)
    while pending:
        response = client.batch_get_image(repositoryName=args.repository, imageIds=[{'imageDigest': d} for d in pending])
        if response.get('failures'):
            raise RuntimeError(f'Cannot resolve protected images: {response["failures"]}')
        pending = []
        for item in response['images']:
            for child in json.loads(item['imageManifest']).get('manifests', []):
                if child['digest'] not in keep:
                    keep.add(child['digest'])
                    pending.append(child['digest'])
    candidates = [i for i in images if i['imageDigest'] not in keep]
    # Delete indexes first; AWS will reject child removal while another index refers to it.
    candidates.sort(key=lambda i: 0 if 'index' in i.get('imageManifestMediaType', '') or 'manifest.list' in i.get('imageManifestMediaType', '') else 1)
    print(json.dumps({'protected': sorted(keep), 'delete': [{'digest': i['imageDigest'], 'tags': i.get('imageTags', [])} for i in candidates]}, indent=2))
    if args.apply:
        for item in candidates:
            result = client.batch_delete_image(repositoryName=args.repository, imageIds=[{'imageDigest': item['imageDigest']}])
            if result.get('failures'):
                raise RuntimeError(f'ECR cleanup failed: {result["failures"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('ECR cleanup failed')
        raise SystemExit(1)
