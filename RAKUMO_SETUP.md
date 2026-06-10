# Rakumo連携 セットアップ手順書（ローカル環境向け）

## 概要

このシステムは、Rakumoカレンダーと **Google Workspace リソースカレンダー** を経由して連携します。  
RakumoカレンダーはGoogle Calendarとリアルタイム双方向同期しているため、  
Google Calendar API を通じてRakumoの会議室予約を取得・比較できます。

**認証方式：サービスアカウント認証**（ユーザーごとのOAuthログイン不要）

> **前提**：このドキュメントはローカル環境（`http://localhost`）での作業を想定しています。

---

## 全体の流れ

```
STEP 1: Google Cloud でAPIを有効化
STEP 2: サービスアカウントにドメイン全体の委任を設定（管理コンソール）
STEP 3: サービスアカウントJSONをプロジェクトに配置
STEP 4: .env に管理者メールアドレスを設定
STEP 5: 会議室のカレンダーIDを取得
STEP 6: システムでカレンダーIDを設定・接続テスト
STEP 7: 差分確認
```

---

## STEP 1: Google Cloud で API を有効化（担当者が行う）

1. `https://console.cloud.google.com` にアクセス
2. プロジェクト「roomreserve-498906」を選択
3. 「APIとサービス」→「ライブラリ」から以下を有効化：
   - **Google Calendar API**
   - **Admin SDK API**

---

## STEP 2: サービスアカウントにドメイン全体の委任を設定（担当者が行う）

サービスアカウント（`roomreserve@roomreserve-498906.iam.gserviceaccount.com`）が  
Google Workspaceのリソースカレンダーにアクセスできるよう、管理コンソールで委任設定を行います。

1. `https://admin.google.com` にアクセス（Google Workspace 管理者アカウントで）
2. 「セキュリティ」→「アクセスとデータ管理」→「APIの制御」
3. 「ドメイン全体の委任を管理する」→「新しく追加」
4. 以下を入力：

   **クライアントID**：`113827268367000422711`

   **OAuthスコープ**（以下をカンマ区切りで入力）：
   ```
   https://www.googleapis.com/auth/calendar.readonly,https://www.googleapis.com/auth/admin.directory.resource.calendar
   ```

5. 「承認」をクリック

> ⚠ この設定はGoogle Workspace管理者のみが行えます。

---

## STEP 3: サービスアカウントJSONをプロジェクトに配置

サービスアカウントのJSONキーファイルはすでに以下に配置済みです：

```
tko10_reserve_rooms/
└── credentials/
    └── service_account.json   ← 配置済み
```

> ⚠ `credentials/` フォルダは `.gitignore` に追加済みです。Gitにコミットされません。

---

## STEP 4: .env に管理者メールアドレスを設定

プロジェクトルートの `.env` ファイルに以下を追加します：

```
GOOGLE_DELEGATED_ADMIN=（Google Workspaceの管理者メールアドレス）
```

例：
```
GOOGLE_DELEGATED_ADMIN=admin@yourdomain.com
```

> ドメイン全体の委任では、サービスアカウントがこのメールアドレスのユーザーとして動作します。  
> Google Workspace の管理者アカウントのメールアドレスを設定してください。

`GOOGLE_SERVICE_ACCOUNT_FILE` はデフォルトで `credentials/service_account.json` を参照するため、  
JSONを上記パスに配置している場合は設定不要です。

---

## STEP 5: 会議室のカレンダーIDを取得（担当者が行う）

1. `https://admin.google.com` にアクセス（管理者アカウントで）
2. 「ディレクトリ」→「建物とリソース」→「リソースを管理」
3. 対象の会議室リソースをクリック
4. 「リソースのメール」または「カレンダーID」をコピー
   （例: `c_xxxxxxxxxxxx@resource.calendar.google.com`）
5. 会議室ごとにIDをメモして共有してもらう

---

## STEP 6: システムでカレンダーIDを設定・接続テスト

### 6-1. ローカルサーバーを起動

```bash
python manage.py migrate   # まだの場合
python manage.py runserver
```

### 6-2. Rakumo連携設定ページを開く

`http://localhost/admin-panel/rakumo/` にアクセス（管理者アカウントでログイン済みであること）

### 6-3. カレンダーIDを入力・保存

各会議室に対応するカレンダーIDを入力して「カレンダーIDを保存」をクリック。

### 6-4. 接続テスト

「接続テスト」ボタンをクリックして「✓ 接続OK（直近7日: N件）」と表示されれば成功。

---

## STEP 7: 差分確認

`http://localhost/admin-panel/rakumo/diff/` にアクセス。  
会議室・期間を選択して「差分を確認する」をクリック。

結果が3カテゴリで表示されます：
- 🟢 **一致**：両システムに同じ予約あり
- 🟠 **Rakumoのみ**：Rakumoにあってこのシステムにない予約
- 🔵 **このシステムのみ**：このシステムにあってRakumoに未反映の予約

---

## トラブルシューティング

### 「サービスアカウントJSONが見つかりません」
- `credentials/service_account.json` が存在するか確認してください

### 「GOOGLE_DELEGATED_ADMIN が設定されていません」
- `.env` に `GOOGLE_DELEGATED_ADMIN=admin@yourdomain.com` を追記してください

### 「403 アクセス権限がありません」
- STEP 2 のドメイン全体の委任設定が完了しているか確認してください
- 委任設定後、反映に数分かかる場合があります

### 「404 カレンダーが見つかりません」
- カレンダーIDが正しいか確認してください（`@resource.calendar.google.com` 形式）

### 「401 認証エラー」
- サービスアカウントJSONの内容が正しいか確認してください
- `GOOGLE_DELEGATED_ADMIN` に指定したメールアドレスが有効なGoogle Workspaceアカウントか確認してください

### 差分件数が多い（初回）
- リザブローからの移行直後は差分が多く出ます
- 今後はこのシステムを主として運用することで差分が解消されます

---

## 今後の拡張予定

| フェーズ | 内容 | 状態 |
|---|---|---|
| Step 1 | 差分確認機能 | ✅ 完了 |
| Step 2 | このシステム→Googleへの自動書き込み | 📋 計画中 |
| Step 3 | Google→このシステムへの変更取り込み（Webhook） | 📋 計画中 |
| Step 4 | 重複検知時の自動アラート通知 | 📋 計画中 |
