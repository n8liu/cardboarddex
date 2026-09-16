# Tunnel-only API service migration

The production API is published at `https://api.cardboarddex.app` through Cloudflare Tunnel. The `cloudflared` container runs beside FastAPI in the AWS ECS task, so inbound API traffic reaches FastAPI locally without an AWS Application Load Balancer. This was verified by starting the replacement task, observing four registered Tunnel connections, requesting the production `/health` endpoint, and finding that request in the replacement FastAPI log. A route aimed at the generated `*.on.aws` URL would still need the ALB.

## Replacement service

- ECS cluster: `default`, region: `us-west-2`.
- Standard Fargate service: `cardboarddex-api-tunnel-service`, staged at desired count `0`, no load balancer. Set desired count to `1` for cutover.
- Task definition: `cardboarddex-api-tunnel:1`, 256 CPU units and 512 MiB memory, `awsvpc` network mode. It preserves the `Main` FastAPI container and `cloudflared` sidecar configuration, with both containers essential so ECS replaces the task if either exits.
- Use the existing four public subnets in `vpc-0eb3f8046811e607d` with `assignPublicIp=ENABLED`. This retains one billable task IPv4 address for outbound Cloudflare, TCG API, eBay, ECR, and S3 connections; no NAT gateway is added.
- Use the separate `/ecs/cardboarddex-api-tunnel` CloudWatch log group with 14-day retention. The Express-owned log group may be removed with its service.
- The service uses outbound-only security group `sg-08030298585b352b4`, with no inbound public listener. RDS allows this group on TCP 5432. It does not depend on the Express-managed task security group, which may be removed when Express Mode is deleted.
- Copy the current task definition directly through AWS APIs without writing its environment values or Tunnel token into this repository or command output. The current task definition stores these values in container environment entries, so take care when inspecting it.

## Cutover checks

1. Register the replacement task definition, security group, and standard service. Start one new task while the Express task remains live, then wait for ECS stability and a connected Tunnel replica. This briefly increases Fargate and public IPv4 usage.
2. Verify `GET /health`, a real `GET /cards/search`, an image request, and a CORS preflight at `api.cardboarddex.app` while the new task is running. The `/health` routing and healthy connector registration have already passed once; repeat the full checks at cutover.
3. Deploy the frontend URL changes and verify `cardboarddex.app` no longer emits the generated AWS endpoint. `NEXT_PUBLIC_API_URL` is baked into the Next.js browser build, so updating a Pages variable without a new build is insufficient.
4. Point backend CI/CD at `cardboarddex-api-tunnel-service` and confirm a subsequent image push redeploys this service. Verify the Celery worker deployment target independently.
5. Delete the Express Mode service **only after** the Tunnel, frontend, and deployment checks pass. AWS deletes its tasks and managed ALB, listener, target groups, and associated resources. Verify the ALB is gone and its four public IPv4 addresses have been released. Check Cost Explorer after billing data catches up.

Run the opt-in deployment smoke tests before deleting Express Mode:

```bash
cd backend
RUN_LIVE_DEPLOYMENT_TESTS=1 \
AWS_BACKEND_URL=https://ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws \
pytest -m live tests/test_deployment_endpoints.py -v
```

This checks Cloudflare health, catalog search, production CORS, direct AWS health, and catalog parity between Cloudflare and AWS. After Express Mode is deleted, omit `AWS_BACKEND_URL`; the two direct-AWS migration checks will skip while the three Cloudflare checks continue to run:

```bash
cd backend
RUN_LIVE_DEPLOYMENT_TESTS=1 pytest -m live tests/test_deployment_endpoints.py -v
```

Before deletion, rollback is simple: keep the Express task running, scale the standard service to zero, and restore the prior frontend build if needed. After deletion, restoring the generated AWS endpoint requires recreating an Express service and ALB; the Tunnel-only service remains the primary API path. The Celery/Redis service and RDS stay running throughout.

The current ALB usage rate is about $0.0225/hour and AWS public IPv4 is $0.005/address-hour. Removing the ALB and its currently observed four addresses would avoid roughly $30.60 per 30-day month before variable LCU charges. This is an estimate, not a bill credit; the API task, its own public IPv4 address, the Celery worker, and RDS remain billable.
