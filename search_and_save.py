"""
福岡中小企業 営業先候補 自動収集・AI精査・Notion保存スクリプト
朝晩2回 GitHub Actions から自動実行される
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic

# ── 設定 ────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY    = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
SERPER_API_KEY    = os.environ["SERPER_API_KEY"]

client = Anthropic(api_key=ANTHROPIC_API_KEY)
JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
SESSION = "朝" if NOW.hour < 12 else "夜"

# ── ① 検索：Web + SNS ───────────────────────────────
def search_web(query: str) -> list[dict]:
    """Serper API で Google 検索"""
    res = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "jp", "hl": "ja", "num": 10}
    )
    results = res.json().get("organic", [])
    return [{"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link")} for r in results]

def search_news(query: str) -> list[dict]:
    """Serper API でニュース検索"""
    res = requests.post(
        "https://google.serper.dev/news",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "jp", "hl": "ja", "num": 10}
    )
    results = res.json().get("news", [])
    return [{"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link"), "date": r.get("date")} for r in results]

def collect_candidates() -> str:
    """複数クエリで幅広く収集し、生データをテキストで返す"""
    queries = [
        "福岡 中小企業 新規事業 2024 2025",
        "福岡 スタートアップ 資金調達 採用",
        "福岡市 企業 DX デジタル化 課題",
        "福岡 中小企業 経営者 インタビュー",
        "福岡 ベンチャー 拡大 成長",
    ]
    all_results = []
    for q in queries:
        all_results += search_web(q)
        all_results += search_news(q)

    # 重複除去（URLベース）
    seen = set()
    unique = []
    for r in all_results:
        if r.get("link") not in seen:
            seen.add(r.get("link"))
            unique.append(r)

    return json.dumps(unique, ensure_ascii=False, indent=2)

# ── ② Claude：初回整理＆スコアリング ────────────────
def first_scoring(raw_data: str) -> str:
    prompt = f"""
あなたは優秀な営業リサーチャーです。
以下の検索結果から「福岡の中小企業」の営業先候補を抽出・整理してください。

【出力形式】JSON配列で以下を含むこと：
- company_name: 企業名
- industry: 業種
- reason: 営業先として有望な理由（具体的に）
- pain_point: 推定される課題・ニーズ
- source_url: 情報源URL
- initial_score: 営業優先度スコア（1〜10）
- score_reason: スコアの根拠

【検索結果】
{raw_data}

企業名が不明なものは除外。最大15件まで。JSONのみ返すこと。
"""
    res = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.content[0].text

# ── ③ Claude（批評家モード）：クリティカル精査 ────────
def critical_review(candidates_json: str) -> str:
    prompt = f"""
あなたは厳格な営業戦略コンサルタントです。
以下の営業先候補リストを**懐疑的・批判的な視点**で精査してください。

【精査の観点】
- 情報が古い・曖昧ではないか？
- 本当に営業価値があるか？（規模・予算感・決裁権）
- 既存競合が既に入り込んでいる可能性は？
- ニーズが本当に存在するか確認できるか？
- 連絡・アプローチが現実的か？

【出力形式】同じJSON配列に以下フィールドを追加：
- critic_issues: 問題点・懸念点のリスト
- credibility: 情報信頼度（high/medium/low）
- should_keep: 最終候補に残すべきか（true/false）
- critic_note: 総合コメント

【候補リスト】
{candidates_json}

JSONのみ返すこと。
"""
    res = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.content[0].text

# ── ④ Claude：最終スコアリング＆ランク付け ──────────
def final_scoring(reviewed_json: str) -> list[dict]:
    prompt = f"""
あなたは営業戦略の専門家です。
批評家AIの精査結果を踏まえ、最終的な営業先リストを作成してください。

【ルール】
- should_keep が false のものは除外
- credibility が low のものは原則除外
- 残ったものを最終スコア（1〜10）で再評価
- アプローチ方法の具体的な提案を追加
- 最終的に優先度順（高い順）に並べる

【出力形式】JSON配列：
- company_name, industry, pain_point, source_url（既存フィールド引き継ぎ）
- final_score: 最終スコア（1〜10）
- approach: 具体的なアプローチ方法・切り口（2〜3文）
- timing: アプローチのベストタイミング・理由
- rank: 順位（1位〜）

【精査済みリスト】
{reviewed_json}

JSONのみ返すこと。
"""
    res = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = res.content[0].text.strip()
    # JSON部分を抽出
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()
    return json.loads(text)

# ── ⑤ Notion保存 ────────────────────────────────────
def save_to_notion(final_leads: list[dict]):
    today_str = NOW.strftime("%Y-%m-%d")
    title = f"{today_str} {SESSION}の部｜福岡営業先候補"

    # ページコンテンツを構築
    children = []

    # ヘッダー
    children.append({
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"🤖 AI三段階精査済み｜{NOW.strftime('%Y/%m/%d %H:%M')} 自動生成｜{len(final_leads)}社"}}],
            "icon": {"emoji": "📊"}, "color": "blue_background"
        }
    })

    children.append({
        "object": "block", "type": "divider", "divider": {}
    })

    # 各企業ブロック
    for i, lead in enumerate(final_leads, 1):
        score = lead.get("final_score", "?")
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"

        # 企業名見出し
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{emoji} #{i} {lead.get('company_name', '不明')}　スコア: {score}/10"
            }}]}
        })

        # 詳細テーブル風ブロック
        details = [
            ("🏭 業種", lead.get("industry", "-")),
            ("😰 課題・ニーズ", lead.get("pain_point", "-")),
            ("🎯 アプローチ方法", lead.get("approach", "-")),
            ("⏰ タイミング", lead.get("timing", "-")),
            ("🔗 情報源", lead.get("source_url", "-")),
        ]
        for label, value in details:
            children.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [
                    {"type": "text", "text": {"content": f"{label}：{value}"}}
                ]}
            })

        children.append({"object": "block", "type": "divider", "divider": {}})

    # フッター
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"次回更新: {'夜20時' if SESSION == '朝' else '翌朝6時'}",
        }, "annotations": {"color": "gray"}}]}
    })

    # Notion APIでページ作成
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "title": {"title": [{"text": {"content": title}}]}
        },
        "children": children
    }

    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        },
        json=payload
    )

    if res.status_code == 200:
        page_url = res.json().get("url", "")
        print(f"✅ Notion保存完了: {page_url}")
    else:
        print(f"❌ Notion保存失敗: {res.status_code} {res.text}")
        raise Exception("Notion API error")

# ── メイン実行 ───────────────────────────────────────
def main():
    print(f"🚀 [{NOW.strftime('%Y-%m-%d %H:%M')} JST] {SESSION}の部 開始")

    print("① 検索中...")
    raw_data = collect_candidates()

    print("② 初回スコアリング中...")
    first_result = first_scoring(raw_data)

    print("③ クリティカル精査中...")
    reviewed = critical_review(first_result)

    print("④ 最終スコアリング中...")
    final_leads = final_scoring(reviewed)
    print(f"   → {len(final_leads)}社が最終候補")

    print("⑤ Notionに保存中...")
    save_to_notion(final_leads)

    print("✅ 完了！")

if __name__ == "__main__":
    main()
