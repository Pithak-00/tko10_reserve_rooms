#!/bin/bash
set -e
echo "=== ApplicationStart started: $(date) ==="

APP_DIR="/home/ec2-user/app"
DATA_DIR="/home/ec2-user/persistent_data"
AWS_DEFAULT_REGION="ap-northeast-1"
S3_BUCKET="tko10-db-backup"
S3_PREFIX="tko10/db"

cd "$APP_DIR"

# ECRイメージURIを取得
IMAGE_URI=$(cat "$APP_DIR/imagedefinitions.json" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)[0]['imageUri'])")
echo "Image URI: $IMAGE_URI"

# 既存コンテナを停止・クリーンアップ（ポート競合を防ぐ）
echo "--- Cleaning up existing containers ---"
sudo -E -u root /usr/bin/docker compose down || true
sudo docker stop $(sudo docker ps -q) 2>/dev/null || true
sudo docker rm -f $(sudo docker ps -aq) 2>/dev/null || true
sudo -E -u root /usr/bin/docker system prune -a -f
sudo -E -u root /usr/bin/docker builder prune -a -f

# SSMから .env を取得
echo "--- Fetching .env from SSM ---"
mkdir -p "$DATA_DIR"
aws ssm get-parameter \
  --name "/tko10/prod/env" \
  --with-decryption \
  --region "$AWS_DEFAULT_REGION" \
  --query "Parameter.Value" \
  --output text > "$DATA_DIR/.env"
sudo cp "$DATA_DIR/.env" "$APP_DIR/.env"

# SSMから service_account.json を取得
echo "--- Fetching service_account.json from SSM ---"
mkdir -p "$APP_DIR/credentials"
aws ssm get-parameter \
  --name "/tko10/prod/service_account_json" \
  --with-decryption \
  --region "$AWS_DEFAULT_REGION" \
  --query "Parameter.Value" \
  --output text > "$APP_DIR/credentials/service_account.json"

# .envのSHUTDOWN_TIME_UTCを読み込んでcronを自動登録（/etc/cron.d/でroot実行）
echo "--- Registering shutdown cron ---"
SHUTDOWN_TIME_UTC=$(grep '^SHUTDOWN_TIME_UTC=' "$APP_DIR/.env" | cut -d'=' -f2-)
if [ -n "$SHUTDOWN_TIME_UTC" ]; then
  SHUTDOWN_HOUR=$(echo "$SHUTDOWN_TIME_UTC" | cut -d: -f1)
  SHUTDOWN_MIN=$(echo "$SHUTDOWN_TIME_UTC" | cut -d: -f2)
  echo "${SHUTDOWN_MIN} ${SHUTDOWN_HOUR} * * * root /home/ec2-user/app/scripts/shutdown_server.sh >> /var/log/tko10_shutdown.log 2>&1" \
    | sudo tee /etc/cron.d/tko10-shutdown > /dev/null
  sudo chmod 644 /etc/cron.d/tko10-shutdown
  echo "Cron registered: ${SHUTDOWN_MIN} ${SHUTDOWN_HOUR} UTC daily"
else
  echo "SHUTDOWN_TIME_UTC not set, skipping cron registration"
fi

# ECRにログインしてイメージをpull
echo "--- Pulling ECR image ---"
ECR_REGISTRY=$(echo "$IMAGE_URI" | cut -d'/' -f1)
aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | \
  sudo docker login --username AWS --password-stdin "$ECR_REGISTRY"
sudo docker pull "$IMAGE_URI"

# APP_IMAGE環境変数を設定
export APP_IMAGE=$IMAGE_URI

# PostgreSQLコンテナのみ先に起動（DB・ユーザーはdocker-composeが自動作成）
echo "--- Starting PostgreSQL container ---"
sudo -E /usr/bin/docker compose up -d db

# PostgreSQL起動待ち（最大60秒）
echo "--- Waiting for PostgreSQL to be ready ---"
for i in $(seq 1 30); do
  if sudo docker exec tko10-postgres pg_isready -U tko10_user 2>/dev/null; then
    echo "PostgreSQL is ready"
    break
  fi
  echo "Waiting... ($i/30)"
  sleep 2
done

# S3にバックアップがあればリストア、なければ空DBで起動
echo "--- Checking S3 for backup ---"
RESTORE_FILE="/tmp/tko10_restore.dump"
if aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/latest.dump" --region "$AWS_DEFAULT_REGION" 2>/dev/null; then
  echo "--- Downloading latest.dump from S3 ---"
  aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/latest.dump" "$RESTORE_FILE" \
    --region "$AWS_DEFAULT_REGION"

  echo "--- Restoring database ---"
  sudo docker cp "$RESTORE_FILE" tko10-postgres:/tmp/restore.dump
  sudo docker exec tko10-postgres \
    pg_restore -U tko10_user -d tko10_db -c --if-exists /tmp/restore.dump || true
  sudo docker exec tko10-postgres rm /tmp/restore.dump
  rm "$RESTORE_FILE"
  echo "Database restored successfully"
else
  echo "No backup found in S3. Starting with empty database."
fi

# 全コンテナ起動（Django）
echo "--- Starting all containers ---"
sudo -E /usr/bin/docker compose up -d

sleep 5

# マイグレーション実行（新規マイグレーションがある場合に対応）
echo "--- Running migrations ---"
sudo -E /usr/bin/docker compose exec -T django python manage.py migrate --noinput || true

sudo chown -R ec2-user:ec2-user "$APP_DIR"
sudo chmod -R 755 "$APP_DIR"

echo "=== ApplicationStart completed: $IMAGE_URI ==="
