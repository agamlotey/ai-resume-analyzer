#!/usr/bin/env bash
# Deletes everything deploy.sh created, to save lab budget.
set -euo pipefail

STACK="${STACK:-resume-analyzer}"
REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$REGION"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

FILES_BUCKET="resume-analyzer-files-$ACCOUNT-$REGION"
CODE_BUCKET="resume-analyzer-code-$ACCOUNT-$REGION"

empty_bucket() {
  local bucket="$1"
  aws s3api head-bucket --bucket "$bucket" 2>/dev/null || return 0
  echo "==> Emptying s3://$bucket"
  python3 - "$bucket" <<'PY'
import sys, boto3
bucket = boto3.resource("s3").Bucket(sys.argv[1])
bucket.object_versions.delete()
bucket.objects.delete()
PY
}

empty_bucket "$FILES_BUCKET"
echo "==> Deleting stack $STACK"
aws cloudformation delete-stack --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --stack-name "$STACK"
empty_bucket "$CODE_BUCKET"
aws s3api delete-bucket --bucket "$CODE_BUCKET" 2>/dev/null || true
echo "Done. All resources removed."
