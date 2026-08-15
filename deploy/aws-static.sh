#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

stack_name="ni-model-static"
region="eu-west-2"
refresh=false

usage() {
  echo "Usage: deploy/aws-static.sh [--stack NAME] [--region REGION] [--refresh-recordings]"
}

while (($#)); do
  case "$1" in
    --stack) stack_name="$2"; shift 2 ;;
    --region) region="$2"; shift 2 ;;
    --refresh-recordings) refresh=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v aws >/dev/null || { echo "Missing dependency: AWS CLI v2." >&2; exit 1; }
aws sts get-caller-identity >/dev/null

build_args=()
$refresh && build_args+=(--refresh-recordings)
scripts/build_static_site.sh "${build_args[@]}"

aws cloudformation deploy \
  --region "$region" \
  --stack-name "$stack_name" \
  --template-file deploy/aws-static-site.yaml \
  --no-fail-on-empty-changeset

bucket="$(aws cloudformation describe-stacks --region "$region" --stack-name "$stack_name" \
  --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' --output text)"
distribution_id="$(aws cloudformation describe-stacks --region "$region" --stack-name "$stack_name" \
  --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' --output text)"
site_url="$(aws cloudformation describe-stacks --region "$region" --stack-name "$stack_name" \
  --query 'Stacks[0].Outputs[?OutputKey==`SiteUrl`].OutputValue' --output text)"

aws s3 sync build/static-site "s3://$bucket" --delete --region "$region"
aws cloudfront create-invalidation --distribution-id "$distribution_id" --paths '/*' >/dev/null

echo "AWS deployment submitted: $site_url"
