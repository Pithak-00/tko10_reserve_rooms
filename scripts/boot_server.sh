#!/bin/bash
# boot_server.sh - EC2起動時にsystemdから自動実行されるスクリプト
# 用途：停止→起動サイクルでのコンテナ自動再開
# ※ start_server.sh（CodeDeploy用）とは別物。pruneなしで高速起動。
set -xe
APP_DIR="/home/ec2-user/app"
DATA_DIR="/home/ec2-user/persistent_data"
AWS_DEFAULT_REGION="ap-northeast-1"

echo "=== Boot start: $(date) ==="

# SSMから .env を取得（停止中に更新された可能性があるため毎回取得）
aws ssm get-parameter \
  --name "/tko10/prod/env" \
  --with-decryption \
  --region $AWS_DEFAULT_REGION \
  --query "Parameter.Value" \
  --output text \
  > $DATA_DIR/.env

# SSMから service_account.json を取得
mkdir -p $APP_DIR/credentials
aws ssm get-parameter \
  --name "/tko10/prod/service_account_json" \
  --with-decryption \
  --region $AWS_DEFAULT_REGION \
  --query "Parameter.Value" \
  --output text \
  > $APP_DIR/credentials/service_account.json

# .env をアプリディレクトリにコピー
cp $DATA_DIR/.env $APP_DIR/.env

# ECRにログイン（キャッシュされたイメージを使用するため docker pull は不要）
IMAGE_URI=$(cat $APP_DIR/imagedefinitions.json | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['imageUri'])")
ECR_REGISTRY=$(echo $IMAGE_URI | cut -d'/' -f1)

aws ecr get-login-password --region $AWS_DEFAULT_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# コンテナ起動（イメージはキャッシュ済みのため高速）
export APP_IMAGE=$IMAGE_URI
cd $APP_DIR
docker compose up -d

echo "=== Boot completed: $IMAGE_URI ==="
