#!/bin/bash
set -xe
echo "ApplicationStart started"
APP_DIR="/home/ec2-user/app"          # 必須：この行がないとスクリプトが失敗する
DATA_DIR="/home/ec2-user/persistent_data"
AWS_DEFAULT_REGION="ap-northeast-1"
cd "$APP_DIR"
 
# ECRイメージURIを取得
IMAGE_URI=$(cat $APP_DIR/imagedefinitions.json | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['imageUri'])")
 
# 既存コンテナを停止・クリーンアップ（ポート競合を防ぐため全コンテナ強制停止）
sudo -E -u root /usr/bin/docker compose down || true
sudo docker stop $(sudo docker ps -q) 2>/dev/null || true
sudo docker rm -f $(sudo docker ps -aq) 2>/dev/null || true
sudo -E -u root /usr/bin/docker system prune -a -f
sudo -E -u root /usr/bin/docker builder prune -a -f
 
# .env を復元（db.sqlite3 は PostgreSQL 移行により不要）
sudo cp $DATA_DIR/.env $APP_DIR/.env
 
# ECRにログインしてイメージをpull
ECR_REGISTRY=$(echo $IMAGE_URI | cut -d'/' -f1)
aws ecr get-login-password --region $AWS_DEFAULT_REGION | \
  sudo docker login --username AWS --password-stdin $ECR_REGISTRY
sudo docker pull $IMAGE_URI
 
# APP_IMAGE環境変数を設定してコンテナ起動（--buildなし：ECRイメージをそのまま使用）
export APP_IMAGE=$IMAGE_URI
sudo -E /usr/bin/docker compose up -d
 
sudo chown -R ec2-user:ec2-user $APP_DIR
sudo chmod -R 755 $APP_DIR
sleep 5
echo "ApplicationStart completed: $IMAGE_URI"
