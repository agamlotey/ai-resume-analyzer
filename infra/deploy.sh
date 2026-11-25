#!/usr/bin/env bash
# Builds the whole cloud stack in the AWS Academy Sandbox (run it in the lab terminal or CloudShell).
set -euo pipefail

STACK="${STACK:-resume-analyzer}"
REGION="${AWS_REGION:-us-east-1}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@demo.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin12345}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.micro}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-3}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export AWS_DEFAULT_REGION="$REGION"

echo "==> Checking AWS access"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "    account $ACCOUNT, region $REGION"

ART_BUCKET="resume-analyzer-code-$ACCOUNT-$REGION"
echo "==> Uploading application code to s3://$ART_BUCKET"
if ! aws s3api head-bucket --bucket "$ART_BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$ART_BUCKET" >/dev/null
  else
    aws s3api create-bucket --bucket "$ART_BUCKET" --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  fi
fi
CODE_KEY="releases/app-$(date +%Y%m%d-%H%M%S).tgz"
TMP_TGZ="$(mktemp -d)/app.tgz"
tar czf "$TMP_TGZ" --exclude='__pycache__' backend frontend
aws s3 cp "$TMP_TGZ" "s3://$ART_BUCKET/$CODE_KEY" --only-show-errors

echo "==> Finding the default VPC and two public subnets"
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
  echo "No default VPC found. Create one with: aws ec2 create-default-vpc" >&2
  exit 1
fi
SUBNETS=$(aws ec2 describe-subnets \
  --filters Name=vpc-id,Values="$VPC_ID" Name=default-for-az,Values=true \
            Name=availability-zone,Values="${REGION}a,${REGION}b,${REGION}c,${REGION}d" \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',' )
echo "    vpc $VPC_ID, subnets $SUBNETS"

UPDATING=false
if aws cloudformation describe-stacks --stack-name "$STACK" >/dev/null 2>&1; then UPDATING=true; fi

echo "==> Deploying CloudFormation stack '$STACK' (takes about 5 minutes)"
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file infra/template.yaml \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    VpcId="$VPC_ID" \
    SubnetIds="$SUBNETS" \
    CodeBucket="$ART_BUCKET" \
    CodeKey="$CODE_KEY" \
    AdminEmail="$ADMIN_EMAIL" \
    AdminPassword="$ADMIN_PASSWORD" \
    InstanceType="$INSTANCE_TYPE" \
    MinInstances="$MIN_INSTANCES" \
    MaxInstances="$MAX_INSTANCES"

URL=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='AppUrl'].OutputValue" --output text)
ASG=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='AutoScalingGroupName'].OutputValue" --output text)

if [ "$UPDATING" = true ]; then
  echo "==> Replacing running instances so they pick up the new code"
  aws autoscaling start-instance-refresh --auto-scaling-group-name "$ASG" \
    --preferences MinHealthyPercentage=0,InstanceWarmup=60 >/dev/null 2>&1 || true
  sleep 30
fi

echo "==> Waiting for the app to pass health checks at $URL"
for i in $(seq 1 60); do
  if curl -fs "$URL/api/health" >/dev/null 2>&1; then
    echo
    curl -s "$URL/api/health"; echo
    echo
    echo "App is live:   $URL"
    echo "Admin login:   $ADMIN_EMAIL  (password from ADMIN_PASSWORD)"
    exit 0
  fi
  printf "."
  sleep 10
done
echo
echo "The stack is created but the app is not healthy yet. Wait a minute and open $URL"
echo "To debug, open the instance with Session Manager and run: sudo cat /var/log/app-setup.log"
