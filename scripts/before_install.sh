#!/bin/bash
set -xe
APP_DIR="/home/ec2-user/app"
DATA_DIR="/home/ec2-user/persistent_data"
AWS_DEFAULT_REGION="ap-northeast-1"

# ディレクトリ作成（念のため）
mkdir -p $APP_DIR $DATA_DIR $APP_DIR/credentials

# SSM から .env を取得
aws ssm get-parameter \
  --name "/tko10/prod/env" \
  --with-decryption \
  --region $AWS_DEFAULT_REGION \
  --query "Parameter.Value" \
  --output text \
  > $DATA_DIR/.env

# SSM から service_account.json を取得
aws ssm get-parameter \
  --name "/tko10/prod/service_account_json" \
  --with-decryption \
  --region $AWS_DEFAULT_REGION \
  --query "Parameter.Value" \
  --output text \
  > $APP_DIR/credentials/service_account.json

chown -R ec2-user:ec2-user $APP_DIR $DATA_DIR