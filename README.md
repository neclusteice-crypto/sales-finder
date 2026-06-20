# 🤖 福岡営業先候補 自動収集システム

朝6時・夜20時に自動で福岡の中小企業を検索し、
3段階AIで精査してNotionに保存するシステムです。

---

## ⚡ セットアップ手順（15分で完了）

### Step 1: APIキーを取得する

| サービス | 取得URL | 備考 |
|---------|---------|------|
| Anthropic | https://console.anthropic.com/keys | Claude AI用 |
| Notion | https://www.notion.so/my-integrations | インテグレーション作成 |
| Serper | https://serper.dev | 無料枠100回/月 |

### Step 2: Notionの準備

1. Notionで新しい**データベース**（フルページ）を作成
2. 作成したインテグレーションをデータベースに接続（右上「...」→「コネクト」）
3. データベースのURLから `DATABASE_ID` をコピー
   - URL例: `https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`
   - `?v=` より前の32文字が DATABASE_ID

### Step 3: GitHubリポジトリを作成

```bash
# このフォルダをGitHubにプッシュ
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/あなたのユーザー名/sales-finder.git
git push -u origin main
```

### Step 4: GitHub Secrets を設定

GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」に以下を追加：

| Secret名 | 値 |
|---------|---|
| `ANTHROPIC_API_KEY` | sk-ant-... |
| `NOTION_API_KEY` | secret_... |
| `NOTION_DATABASE_ID` | 32文字のID |
| `SERPER_API_KEY` | ... |

### Step 5: 動作確認

GitHubリポジトリの「Actions」タブ →「営業先候補 自動収集」→「Run workflow」で手動実行してテスト！

---

## 🔄 自動実行スケジュール

| 実行時刻 | 内容 |
|---------|------|
| 毎日 朝6:00 JST | 朝の部：前日夜〜当日朝の情報を収集 |
| 毎日 夜20:00 JST | 夜の部：当日昼〜夕方の情報を収集 |

---

## 🧠 AI処理フロー

```
① 検索（Serper API）
   └── Web検索 × 5クエリ + ニュース検索 × 5クエリ

② Claude（リサーチャーモード）
   └── 企業情報を整理・初回スコアリング（1〜10点）

③ Claude（批評家モード）← ここがポイント！
   └── 懐疑的視点で精査
       - 情報の信頼性は？
       - 本当に営業価値あるか？
       - 競合が既にいないか？

④ Claude（最終判断モード）
   └── 批評を踏まえて最終スコアリング＆アプローチ提案

⑤ Notion保存
   └── 「2025-06-20 朝の部」というページに自動保存
```

---

## 📝 検索クエリのカスタマイズ

`search_and_save.py` の `collect_candidates()` 内の `queries` リストを編集してください：

```python
queries = [
    "福岡 中小企業 新規事業 2024 2025",  # ← 変更OK
    "福岡 スタートアップ 資金調達 採用",
    ...
]
```

---

## 💰 月間コスト目安

| サービス | 月額目安 |
|---------|---------|
| Anthropic API | 約500〜1,500円（実行60回/月） |
| Serper API | 無料枠内（100回）または $50/月プラン |
| GitHub Actions | 無料（パブリックリポジトリ） |
| **合計** | **約500〜2,000円/月** |
