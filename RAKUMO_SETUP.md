# Rakumo連携 セットアップ手順書（ローカル環境向け）

## 概要

このシステムは、Rakumoカレンダーと **Google Workspace リソースカレンダー** を経由して連携します。  
RakumoカレンダーはGoogle Calendarとリアルタイム双方向同期しているため、  
Google Calendar API を通じてRakumoの会議室予約を取得・比較できます。

> **前提**：このドキュメントはローカル環境（`http://localhost`）での作業を想定しています。

---

## Step 1: Google Cloud Console での設定（担当者が行う）

### 1-1. プロジェクト確認
既存のプロジェクト（Google OAuth連携で使用中のもの）を引き続き使用します。  
`https://console.cloud.google.com/` → 対象プロジェクトを選択。

### 1-2. Google Calendar API の有効化
1. 「APIとサービス」→「ライブラリ」
2. 「Google Calendar API」を検索 → **有効にする**
3. （すでに有効な場合はスキップ）

### 1-3. OAuthスコープの追加
1. 「APIとサービス」→「OAuth同意画面」
2. 「スコープを追加または削除」をクリック
3. 以下のスコープを追加：
   - `https://www.googleapis.com/auth/calendar.readonly`  
     （読み取りのみ。差分確認だけなら十分）
   - または既存の `https://www.googleapis.com/auth/calendar.events` でも可

> ⚠ スコープを変更した場合、ユーザーは **再認証（再ログイン）** が必要です。

### 1-4. ローカル環境用リダイレクトURIの追加
ローカルで OAuth 認証を動かすには、Google Cloud Console に `localhost` のリダイレクトURIを登録する必要があります。

1. 「APIとサービス」→「認証情報」→ 対象の OAuth クライアントIDをクリック
2. 「承認済みのリダイレクト URI」に以下を追加：
   ```
   http://localhost/reservations/auth/google/callback/
   ```
3. 「保存」をクリック

> ⚠ `http://` （HTTPSではなく HTTP）で登録してください。localhostはHTTPが許可されています。

---

## Step 2: ローカル環境の `.env` 設定

プロジェクトルート（`manage.py` と同じフォルダ）に `.env` ファイルを作成し、以下を記載します：

```
GOOGLE_CLIENT_ID=（Google Cloud Console で取得したクライアントID）
GOOGLE_CLIENT_SECRET=（同上、クライアントシークレット）
GOOGLE_REDIRECT_URI=http://localhost/reservations/auth/google/callback/
```

> クライアントIDとシークレットは、Google Cloud Console →「APIとサービス」→「認証情報」→ 対象OAuthクライアント で確認できます。

---

## Step 3: Google Workspace 管理コンソールでの確認（担当者が行う）

### 3-1. 会議室リソースのカレンダーIDを確認

1. `https://admin.google.com` にアクセス（Google Workspace 管理者アカウントで）
2. 「ディレクトリ」→「建物とリソース」→「リソースを管理」
3. 対象の会議室リソースをクリック
4. **「カレンダーID」** をコピー（例: `c_xxxxxxxxxxxx@resource.calendar.google.com`）
5. 会議室ごとにIDをメモして共有してもらう

### 3-2. リソースカレンダーの共有設定確認

リソースカレンダーへのアクセスには、以下のいずれかの権限が必要です：

| 権限レベル | 説明 |
|---|---|
| Google Workspace 管理者 | すべてのリソースカレンダーにアクセス可能 |
| 共有設定：「組織内の全員が閲覧可能」 | 一般ユーザーでも閲覧可能 |
| 共有設定：「個別共有」 | 特定ユーザーのみ |

管理コンソール →「カレンダー」→ リソースを選択 →「共有設定」で確認・変更できます。

---

## Step 4: ローカルシステムでの操作

### 4-1. ローカルサーバーを起動
```bash
python manage.py migrate   # マイグレーションがまだの場合
python manage.py runserver
```
ブラウザで `http://localhost` にアクセスできることを確認します。

### 4-2. 管理者アカウントでログイン
`is_staff=True` の管理者アカウントでシステムにログイン。

### 4-3. Google カレンダー連携を有効化
1. 「**自分の予約一覧**」ページ（`http://localhost/reservations/my/`）を開く
2. ページ内の「**Google カレンダー連携**」カードにある「Googleと連携する」ボタンをクリック
3. Googleのログイン画面が開くので、**会社のGoogle Workspaceアカウント**（Rakumoを使っているアカウント）でログイン・承認する
4. 「連携中」バッジが表示されれば完了

> ⚠ ここで使うGoogleアカウントは、Rakumoの会議室リソースにアクセスできるアカウント（Google Workspace 管理者が理想）である必要があります。

### 4-4. Rakumo連携設定ページでカレンダーIDを設定
1. `http://localhost/admin-panel/rakumo/` を開く
2. Step 3-1 で取得した各会議室のカレンダーIDを入力して「保存」
3. 「接続テスト」ボタンをクリックして「✓ 接続OK」になることを確認

### 4-5. 差分確認
1. `http://localhost/admin-panel/rakumo/diff/` を開く
2. 会議室・期間を選択して「差分を確認する」
3. 結果が3カテゴリで表示される：
   - 🟢 **一致**：両システムに同じ予約あり
   - 🟠 **Rakumoのみ**：Rakumoにあってこのシステムにない予約
   - 🔵 **このシステムのみ**：このシステムにあってRakumoに未反映の予約

---

## トラブルシューティング

### OAuth認証後に「リダイレクトURIが一致しません」エラー
- Google Cloud Console のリダイレクトURIに `http://localhost/reservations/auth/google/callback/` が登録されているか確認
- `.env` の `GOOGLE_REDIRECT_URI` が同じ値になっているか確認

### 「403 アクセス権限がありません」
- リソースカレンダーの共有設定を確認してください
- Google Workspace 管理者アカウントで OAuth 認証を行ってください

### 「404 カレンダーが見つかりません」
- カレンダーIDが正しいか確認してください（`@resource.calendar.google.com` で終わる形式）

### 「401 認証エラー」
- 「自分の予約一覧」ページでGoogle連携を一度解除して再連携してください

### 差分件数が多い（初回）
- リザブローからの移行直後は差分が多く出ます
- 今後はこのシステムを主として運用することで差分が解消されます

---

## 今後の拡張予定（Step 2 以降）

| フェーズ | 内容 | 状態 |
|---|---|---|
| Step 1 | 差分確認機能 | ✅ 完了 |
| Step 2 | このシステム→Googleへの自動書き込み | 📋 計画中 |
| Step 3 | Google→このシステムへの変更取り込み（Webhook） | 📋 計画中 |
| Step 4 | 重複検知時の自動アラート通知 | 📋 計画中 |
