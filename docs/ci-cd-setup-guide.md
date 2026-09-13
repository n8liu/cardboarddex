# CardboardDex CI/CD & Deployment Guide

This guide details how to configure GitHub Actions, Cloudflare Pages, and AWS to run automated CI/CD for CardboardDex.

---

## Architecture Summary

- **Frontend**: Next.js 16 App Router hosted on **Cloudflare Pages**.
- **Backend API**: FastAPI (Uvicorn) container running on **AWS ECS Fargate** behind an Application Load Balancer (ALB).
- **Async Workers**: Celery worker container on **AWS ECS Fargate**.
- **Scheduler**: Celery beat container on **AWS ECS Fargate** (running alternating 15-minute price cycling).
- **Database**: PostgreSQL 16 on **Amazon RDS**.
- **Queue / Limiter**: Redis 7 on **Amazon ElastiCache**.
- **CI/CD**: **GitHub Actions** with OpenID Connect (OIDC) authentication to AWS and API token authentication to Cloudflare.

---

## 1. AWS Setup

### 1.1 Create the ECR Repository

In the AWS Console or AWS CLI:

```bash
aws ecr create-repository \
  --repository-name cardboarddex-backend \
  --image-scanning-configuration scanOnPush=true \
  --region us-east-1
```

### 1.2 Configure GitHub Actions OIDC Authentication (Keyless IAM Role)

Using OIDC avoids storing long-lived AWS keys in GitHub.

1. **Add GitHub as an OIDC Identity Provider** (if not already added in your AWS account):
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`

2. **Create IAM Role with Trust Policy**:
   Save this trust policy as `trust-policy.json` (replace `YOUR_GITHUB_ORG/YOUR_REPO` with `n8liu/cardboarddex`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:n8liu/cardboarddex:*"
           }
         }
       }
     ]
   }
   ```

   Create the role:
   ```bash
   aws iam create-role \
     --role-name github-actions-cardboarddex-deploy \
     --assume-role-policy-document file://trust-policy.json
   ```

3. **Attach Permissions Policy**:
   Attach permissions allowing ECR push, ECS task execution, and ECS service updates:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ecr:GetAuthorizationToken",
           "ecr:BatchCheckLayerAvailability",
           "ecr:GetDownloadUrlForLayer",
           "ecr:BatchGetImage",
           "ecr:PutImage",
           "ecr:InitiateLayerUpload",
           "ecr:UploadLayerPart",
           "ecr:CompleteLayerUpload"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "ecs:DescribeServices",
           "ecs:UpdateService",
           "ecs:DescribeTaskDefinition",
           "ecs:RegisterTaskDefinition",
           "ecs:RunTask",
           "ecs:DescribeTasks"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": "iam:PassRole",
         "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/ecsTaskExecutionRole*"
       }
     ]
   }
   ```

### 1.3 Amazon ECS Fargate Cluster & Services

1. **Create ECS Cluster**:
   ```bash
   aws ecs create-cluster --cluster-name cardboarddex-cluster
   ```

2. **Backend Services Architecture**:
   - `cardboarddex-api-service`: Runs FastAPI with default CMD (`uvicorn app.main:app --host 0.0.0.0 --port 8000`). Attached to Application Load Balancer target group on port 8000 with healthcheck on `/health`.
   - `cardboarddex-worker-service`: Runs Celery worker with container command override:
     `["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]`
   - `cardboarddex-beat-service`: Runs Celery beat scheduler with container command override:
     `["celery", "-A", "app.celery_app", "beat", "--loglevel=info"]`
   - `cardboarddex-migration`: Task definition for one-off Alembic migrations:
     `["alembic", "upgrade", "head"]`

3. **Environment & Secrets in ECS Task Definition**:
   Inject database and provider secrets via AWS Secrets Manager:
   - `DATABASE_URL`: `postgresql+psycopg2://cardboarddex:<PASSWORD>@<RDS_ENDPOINT>:5432/cardboarddex`
   - `REDIS_URL`: `redis://<ELASTICACHE_ENDPOINT>:6379/0`
   - `TCGAPI_API_KEY`: Secrets Manager ARN
   - `EBAY_CLIENT_ID`: Secrets Manager ARN
   - `EBAY_CLIENT_SECRET`: Secrets Manager ARN
   - `BACKEND_CORS_ORIGINS`: `https://cardboarddex.app,https://www.cardboarddex.app,https://cardboarddex.pages.dev`

---

## 2. Cloudflare Setup

### 2.1 Create Cloudflare Pages Project

1. Log into your [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Navigate to **Workers & Pages** > **Create application** > **Pages**.
3. Create a project named `cardboarddex-frontend`.
4. Under **Settings** > **Environment Variables**, set:
   - `NEXT_PUBLIC_API_URL`: `https://api.cardboarddex.app`
   - `NODE_VERSION`: `20`

### 2.2 Create Cloudflare API Token for GitHub Actions

1. In Cloudflare, navigate to **My Profile** > **API Tokens** > **Create Token**.
2. Select template: **Edit Cloudflare Workers/Pages**.
3. Account Resources: Include your account.
4. Copy the generated token.

---

## 3. GitHub Repository Configuration

In your GitHub repository (`n8liu/cardboarddex`), navigate to **Settings** > **Secrets and variables** > **Actions**.

### 3.1 Repository Secrets

| Secret Name | Description |
| --- | --- |
| `AWS_ROLE_TO_ASSUME` | The ARN of the IAM role created in Step 1.2 (e.g., `arn:aws:iam::123456789012:role/github-actions-cardboarddex-deploy`) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token created in Step 2.2 |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare Account ID (found on the right sidebar of the Cloudflare dashboard) |

### 3.2 Repository Variables

| Variable Name | Default / Example Value | Description |
| --- | --- | --- |
| `AWS_REGION` | `us-east-1` | Target AWS region |
| `ECR_REPOSITORY` | `cardboarddex-backend` | ECR repository name |
| `ECS_CLUSTER` | `cardboarddex-cluster` | ECS Cluster name |
| `ECS_API_SERVICE` | `cardboarddex-api-service` | ECS FastAPI service name |
| `ECS_WORKER_SERVICE` | `cardboarddex-worker-service` | ECS Celery worker service name |
| `ECS_BEAT_SERVICE` | `cardboarddex-beat-service` | ECS Celery beat service name |
| `ECS_MIGRATION_TASK_FAMILY` | `cardboarddex-migration` | Task definition name for Alembic migrations |
| `ECS_SUBNET_IDS` | `subnet-abc,subnet-xyz` | Comma-separated private subnet IDs for migration task |
| `ECS_SECURITY_GROUP_IDS` | `sg-0123456` | Security group allowing access to RDS |
| `NEXT_PUBLIC_API_URL` | `https://api.cardboarddex.app` | Public URL for backend API |
| `CLOUDFLARE_PROJECT_NAME` | `cardboarddex-frontend` | Cloudflare Pages project name |

---

## 4. Workflows Operation

### Pull Requests
- **Frontend Changes**: GitHub Actions runs TypeScript check and build. If Cloudflare credentials are configured, it deploys a Preview deployment and comments the unique preview URL on the pull request.
- **Backend Changes**: Runs `compileall` check and `pytest` suite across all 125 backend tests.

### Merging to `main`
- **Frontend**: Automatically builds and deploys to Cloudflare Pages production environment.
- **Backend**:
  1. Tests pass.
  2. Builds multi-stage Docker image and pushes to Amazon ECR tagged with git commit SHA and `latest`.
  3. Executes one-off Alembic migration task against Amazon RDS.
  4. Triggers zero-downtime rolling update on all ECS services (`api`, `worker`, `beat`).
