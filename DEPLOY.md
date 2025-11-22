# デプロイ手順

## GitHubへのアップロード

1. リポジトリを初期化（まだの場合）
```bash
git init
```

2. ファイルをステージング
```bash
git add .
```

3. コミット
```bash
git commit -m "Initial commit: Money Pocket app"
```

4. リモートリポジトリを追加（GitHubで作成済みの場合）
```bash
git remote add origin <your-repository-url>
```

5. プッシュ
```bash
git branch -M main
git push -u origin main
```

## Renderでのデプロイ

### 手順

1. [Render](https://render.com)にログイン

2. **New +** → **Web Service** を選択

3. GitHubリポジトリを接続
   - GitHubアカウントを連携
   - リポジトリを選択

4. 以下の設定を入力:
   - **Name**: `money-pocket` (任意)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: Free プランでOK

5. **Create Web Service** をクリック

6. デプロイが完了するまで待つ（数分かかります）

### 注意事項

- データベースファイル（`money_pocket.db`）はRenderの一時ストレージに保存されます
- Renderの無料プランでは、一定時間アクセスがないとスリープします
- 本番環境では、PostgreSQLなどの永続的なデータベースの使用を推奨します

### カスタムドメイン（オプション）

1. Renderのダッシュボードでサービスを選択
2. **Settings** → **Custom Domains** から設定可能


