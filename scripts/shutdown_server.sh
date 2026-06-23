#!/bin/bash
# shutdown_server.sh - インスタンス削除前のシャットダウン処理
# 実行順序: Django停止 → PostgreSQL接続切断 → pg_dump → S3保存（2種類）→ 古い履歴削除
# cronはstart_server.shが .env の SHUTDOWN_TIME_UTC を読んで自動登録する

set -e

APP_DIR="/home/ec2-user/app"
AWS_DEFAULT_REGION="ap-northeast-1"
S3_BUCKET="tko10-db-backup"
S3_PREFIX="tko10/db"
DATE=$(date +%Y%m%d)
DATETIME=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/tmp/tko10_${DATETIME}.dump"
RETENTION_DAYS=7

echo "=== Shutdown start: $(date) ==="

# 1. Djangoコンテナを停止（PostgreSQLは残す）
echo "--- Stopping Django container ---"
sudo docker stop tko10-django 2>/dev/null || true
echo "Django stopped"

# 2. PostgreSQLの既存接続を強制切断（静止状態にする）
echo "--- Terminating PostgreSQL connections ---"
sudo docker exec tko10-postgres psql -U tko10_user -d tko10_db -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
   WHERE datname = 'tko10_db' AND pid <> pg_backend_pid();" || true
echo "Connections terminated"

# 3. pg_dump 実行（カスタム形式・シーケンス値含む完全バックアップ）
echo "--- Running pg_dump ---"
sudo docker exec tko10-postgres \
  pg_dump -Fc -U tko10_user tko10_db > "$BACKUP_FILE"
echo "Dump created: $BACKUP_FILE"

# 4. S3にアップロード（戻す用：毎日上書き）
echo "--- Uploading latest.dump ---"
aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/${S3_PREFIX}/latest.dump" \
  --region "$AWS_DEFAULT_REGION"
echo "Uploaded: s3://${S3_BUCKET}/${S3_PREFIX}/latest.dump"

# 5. S3にアップロード（履歴用：日付付きで保存）
echo "--- Uploading history dump ---"
HISTORY_KEY="${S3_PREFIX}/history/tko10_${DATE}.dump"
aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/${HISTORY_KEY}" \
  --region "$AWS_DEFAULT_REGION"
echo "Uploaded: s3://${S3_BUCKET}/${HISTORY_KEY}"

# 6. 7日以上前の履歴を自動削除
echo "--- Cleaning old history (keeping ${RETENTION_DAYS} days) ---"
CUTOFF=$(date -d "${RETENTION_DAYS} days ago" +%Y%m%d)
aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/history/" --region "$AWS_DEFAULT_REGION" | \
  awk '{print $4}' | while read -r FILENAME; do
    FILE_DATE=$(echo "$FILENAME" | grep -oP '\d{8}' | head -1)
    if [ -n "$FILE_DATE" ] && [ "$FILE_DATE" -lt "$CUTOFF" ]; then
      aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/history/${FILENAME}" \
        --region "$AWS_DEFAULT_REGION"
      echo "Deleted old backup: $FILENAME"
    fi
  done
echo "History cleanup completed"

# 7. ローカルの一時ファイルを削除
rm "$BACKUP_FILE"

echo "=== Shutdown completed: $(date) ==="
