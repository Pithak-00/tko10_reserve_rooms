#!/bin/bash
set -xe
APP_DIR="/home/ec2-user/app"
DATA_DIR="/home/ec2-user/persistent_data"
mkdir -p $DATA_DIR
if [ -f "$APP_DIR/.env" ]; then
    cp $APP_DIR/.env $DATA_DIR/.env
fi
# db.sqlite3 のバックアップは PostgreSQL 移行により不要
