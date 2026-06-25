#!/bin/bash

# 【業務用・最終確定パッチ】
sleep 15

# ホストOSの80番ポートを叩くことで、Dockerのマッピング経由で内部のDjango（8000番）に正しく着弾させる。
# リダイレクト（302）を自動追跡（-L）する無敵仕様。
STATUS_CODE=$(curl -s -o /dev/null -L -w "%{http_code}" http://localhost/)

# 200(OK) または 302(Redirect) なら合格（Succeeded）とする
if [ "$STATUS_CODE" -eq 200 ] || [ "$STATUS_CODE" -eq 302 ]; then
    echo "ValidateService Success with Status Code: $STATUS_CODE"
    exit 0
else
    echo "ValidateService Failed with Status Code: $STATUS_CODE"
    exit 1
fi