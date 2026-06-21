"""
九州（福岡メイン）中小企業 海外進出支援サービス向け 営業先候補 自動収集・AI精査・市場調査・Notion保存
対象サービス：東南アジア市場調査・視察代行／インドネシア進出支援／海外向けブランディング／展示会出展支援
朝晩2回 GitHub Actions から自動実行される
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic

# ── 設定 ────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY     = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
SERPER_API_KEY     = os.environ["SERPER_API_KEY"]

client  = Anthropic(api_key=ANTHROPIC_API_KEY)
JST     = timezone(timedelta(hours=9))
NOW     = datetime.now(JST)
SESSION = "朝" if NOW.hour < 12 else "夜"

# ── ① 検索 ───────────────────────────────────────────
def search_web(query: str) -> list[dict]:
    res = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "jp", "hl": "ja", "num": 10}
    )
    results = res.json().get("organic", [])
    return [{"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link")} for r in results]

def search_news(query: str) -> list[dict]:
    res = requests.post(
        "https://google.serper.dev/news",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "gl": "jp", "hl": "ja", "num": 10}
    )
    results = res.json().get("news", [])
    return [{"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link"), "date": r.get("date")} for r in results]

def search_market(industry: str) -> str:
    """業種ごとにインドネシア・ASEAN全体・ラオスの市場をWeb検索"""
    queries = [
        f"{industry} インドネシア 市場規模 2025",
        f"{industry} ASEAN 東南アジア 需要 トレンド",
        f"{industry} ラオス ビジネスチャンス",
    ]
    results = []
    for q in queries:
        results += search_web(q)
    return json.dumps(results[:15], ensure_ascii=False, indent=2)

def collect_candidates() -> str:
    """九州（福岡メイン）小規模企業に絞った収集。進出先優先：インドネシア→ラオス→ASEAN全体"""
    web_queries = [
        # 補助金採択リスト（小規模事業者が多い）
        "小規模事業者持続化補助金 採択 福岡 海外展開",
        "ものづくり補助金 採択 福岡 輸出 海外",
        "新輸出大国コンソーシアム 採択企業 九州 福岡",
        "事業再構築補助金 採択 福岡 海外 ASEAN インドネシア",
        # Wantedly（少人数×海外事業）
        "site:wantedly.com 福岡 海外事業 ASEAN インドネシア 10名",
        "site:wantedly.com 福岡 輸出 東南アジア インドネシア スタートアップ",
        "site:wantedly.com 九州 グローバル インドネシア 創業",
        # クラウドファンディング×海外
        "site:makuake.com 福岡 海外展開 インドネシア ASEAN",
        "site:camp-fire.jp 福岡 九州 越境EC インドネシア",
        # 小規模×海外ニュース
        "福岡 スタートアップ 海外進出 インドネシア 2025",
        "福岡 ベンチャー 創業 輸出 インドネシア ASEAN",
        "九州 小規模企業 海外販路 インドネシア 新規",
        # 地方メディア
        "西日本新聞 福岡 中小 海外進出 インドネシア 2025",
        "福岡経済 小規模 輸出 ASEAN インドネシア",
        # 九州全体
        "九州 中小企業 東南アジア インドネシア 海外進出",
        "熊本 鹿児島 長崎 佐賀 大分 宮崎 製造業 インドネシア 海外展開",
        "九州 企業 インドネシア ラオス ASEAN ビジネス",
    ]
    news_queries = [
        "福岡 スタートアップ インドネシア 海外進出 2025",
        "九州 小規模 ものづくり 輸出 ASEAN 2025",
        "福岡 創業 海外販売 インドネシア ASEAN",
        "九州 ベンチャー インドネシア ラオス 2025",
    ]

    all_results = []
    for q in web_queries:
        all_results += search_web(q)
    for q in news_queries:
        all_results += search_news(q)

    seen, unique = set(), []
    for r in all_results:
        if r.get("link") not in seen:
            seen.add(r.get("link"))
            unique.append(r)

    return json.dumps(unique, ensure_ascii=False, indent=2)

# ── ② Claude：初回整理＆スコアリング ────────────────
def first_scoring(raw_data: str) -> str:
    prompt = f"""
あなたは海外進出支援の営業リサーチャーです。
以下の検索結果から「九州（特に福岡）の小規模企業で海外進出・東南アジア展開に興味がありそうな企業」を抽出・整理してください。

【提供サービス】
- 東南アジア市場調査・視察代行
- インドネシア進出支援
- 海外進出向けブランディング
- インドネシアのイベント・展示会出展支援

【抽出基準】
- 従業員数：5〜50名以下の小規模企業を優先（上場企業・従業員100名超は除外）
- 売上高：1億〜10億円未満の規模感を優先（推定可）
- 設立年数：創業3〜15年以内を優先（老舗大手・上場企業は除外）
- 福岡市・福岡県に拠点がある企業を最優先（スコアに+2点加算イメージ）
- 次点で九州他県（熊本・長崎・鹿児島・佐賀・大分・宮崎）
- 製造業・食品・伝統工芸・テック系など海外展開しやすい業種を優先
- 既に海外展開に関心を示している企業を優先
- 補助金採択企業・Wantedly求人掲載企業・クラファン掲載企業は信頼度を高く評価
- 進出先の優先順位：①インドネシア ②ラオス ③ASEAN全体（ベトナム単体での評価は不要）

【出力形式】JSON配列（最大15件）：
- company_name: 企業名
- location: 所在地（例：福岡市、熊本県など）
- industry: 業種
- website_url: 企業公式サイトURL（不明はnull）
- source_url: 情報源URL
- reason: 有望な理由（具体的に）
- pain_point: 推定される課題・ニーズ
- best_service: 最も刺さりそうなサービス（市場調査/インドネシア進出/ブランディング/展示会支援）
- initial_score: 営業優先度スコア（1〜10）
- score_reason: スコアの根拠

【検索結果】
{raw_data}

企業名が不明なものは除外。JSONのみ返すこと。
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
あなたは厳格な海外ビジネス戦略コンサルタントです。
以下の営業先候補リストを懐疑的・批判的な視点で精査してください。

【精査の観点】
- 情報が古い・信頼性が低くないか？
- 本当に海外進出の意欲・予算があるか？
- 既に他の海外進出支援会社と契約済みの可能性は？
- インドネシア・ラオス・ASEANとの相性は本当にあるか？
- 意思決定スピード・予算感は現実的か？
- アプローチ方法が現実的に存在するか？
- 小規模（従業員50名以下）の企業か？大手・上場は除外推奨。

【出力形式】同じJSON配列に追加：
- critic_issues: 問題点・懸念点リスト（配列）
- credibility: 情報信頼度（high/medium/low）
- should_keep: 最終候補に残すべきか（true/false）
- critic_note: 総合コメント（1〜2文）

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

# ── ④ 市場調査：Web検索＋Claude知識で評価 ──────────
def research_market(company_name: str, industry: str) -> dict:
    """Web検索＋Claudeの知識で3軸（インドネシア・ASEAN全体・ラオス）市場ポテンシャルを評価"""
    market_data = search_market(industry)

    prompt = f"""
あなたは東南アジア市場の専門アナリストです。
以下の企業・業種について、インドネシア・ASEAN全体・ラオスそれぞれの市場ポテンシャルを評価してください。
優先順位はインドネシア→ラオス→ASEAN全体です。ベトナム単体の評価は不要です。

【企業名】{company_name}
【業種】{industry}

【最新Web検索データ】
{market_data}

上記のWeb検索データに加え、あなた自身の東南アジア市場知識も活用して評価してください。

【出力形式】JSONのみ：
{{
  "indonesia": {{
    "score": 市場ポテンシャルスコア（1〜10）,
    "summary": "評価コメント（2〜3文。市場規模・成長率・競合状況・日本製品への親和性を含む）",
    "opportunity": "具体的なビジネスチャンス（1〜2文）",
    "risk": "主なリスク（1文）"
  }},
  "southeast_asia": {{
    "score": スコア（1〜10）,
    "summary": "評価コメント（インドネシア・ラオスを含むASEAN全体の視点で。ベトナム単体は不要）",
    "opportunity": "具体的なビジネスチャンス",
    "risk": "主なリスク"
  }},
  "laos": {{
    "score": スコア（1〜10）,
    "summary": "評価コメント（人口・経済成長・競合の少なさ・インドネシアとの連携可能性等を含む）",
    "opportunity": "具体的なビジネスチャンス",
    "risk": "主なリスク"
  }}
}}

JSONのみ返すこと。
"""
    res = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = res.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()
    try:
        return json.loads(text)
    except Exception:
        return {
            "indonesia":      {"score": "-", "summary": "取得失敗", "opportunity": "-", "risk": "-"},
            "southeast_asia": {"score": "-", "summary": "取得失敗", "opportunity": "-", "risk": "-"},
            "laos":           {"score": "-", "summary": "取得失敗", "opportunity": "-", "risk": "-"},
        }

# ── ⑤ Claude：最終スコアリング＆5社に絞る ──────────
def final_scoring(reviewed_json: str) -> list[dict]:
    prompt = f"""
あなたは海外進出支援の営業戦略専門家です。
批評家AIの精査結果を踏まえ、最終的な営業先リストを作成してください。

【ルール】
- 従業員50名以下・売上10億円未満の小規模企業を優先（大手・上場は原則除外）
- 福岡市・福岡県の企業を優先的に選ぶ（同スコアなら福岡を上位に）
- 進出先の優先順位：①インドネシア ②ラオス ③ASEAN全体（ベトナム単体での評価は不要）
- should_keep が false でも有望なら残してよい
- credibility が low でも他に候補がなければ残す
- 必ず5社選ぶこと（候補が少なくても5社になるまで緩めの基準で選ぶ）
- 残ったものを最終スコア（1〜10）で再評価
- 優先度順（高い順）に並べる

【提供サービス（参考）】
- 東南アジア市場調査・視察代行
- インドネシア進出支援
- 海外進出向けブランディング
- インドネシアのイベント・展示会出展支援

【出力形式】JSON配列（必ず5社以内）：
- company_name, location, industry, website_url, source_url, pain_point, best_service（引き継ぎ）
- final_score: 最終スコア（1〜10）
- approach: 具体的なアプローチ方法・切り口（2〜3文）
- timing: アプローチのベストタイミング・理由（1〜2文）
- rank: 順位（1〜5）

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
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()
    return json.loads(text)

# ── ⑥ Notion保存 ────────────────────────────────────
def make_rich_text(content: str) -> list:
    return [{"type": "text", "text": {"content": str(content) or "-"}}]

def make_link_rich_text(label: str, url: str) -> list:
    if url and str(url).startswith("http"):
        return [{"type": "text", "text": {"content": label, "link": {"url": url}}}]
    return [{"type": "text", "text": {"content": label or "-"}}]

def score_emoji(score) -> str:
    try:
        s = float(score)
        if s >= 8: return "🟢"
        if s >= 5: return "🟡"
        return "🔴"
    except Exception:
        return "⚪"

def save_to_notion(final_leads: list[dict], market_data: dict):
    today_str = NOW.strftime("%Y-%m-%d")
    title = f"{today_str} {SESSION}の部｜九州 海外進出支援 営業先候補 TOP5"

    children = []

    # ヘッダー
    children.append({
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": make_rich_text(f"🤖 AI三段階精査＋市場調査済み｜{NOW.strftime('%Y/%m/%d %H:%M')} 自動生成｜TOP {len(final_leads)}社"),
            "icon": {"emoji": "🌏"}, "color": "blue_background"
        }
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    # 各企業ブロック
    for i, lead in enumerate(final_leads, 1):
        score    = lead.get("final_score", "?")
        emoji    = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        company  = lead.get("company_name", "不明")
        location = lead.get("location", "")
        website  = lead.get("website_url") or ""
        source   = lead.get("source_url") or ""
        mkt      = market_data.get(company, {})
        indo     = mkt.get("indonesia", {})
        sea      = mkt.get("southeast_asia", {})
        laos     = mkt.get("laos", {})

        # 企業名見出し
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": make_link_rich_text(
                f"{emoji} #{i} {company}（{location}）　営業スコア: {score}/10",
                website
            )}
        })

        # 基本情報
        basic_items = [
            ("🏭 業種",          lead.get("industry", "-"),      None),
            ("🎯 刺さるサービス", lead.get("best_service", "-"),  None),
            ("😰 課題・ニーズ",   lead.get("pain_point", "-"),    None),
            ("💡 アプローチ",     lead.get("approach", "-"),      None),
            ("⏰ タイミング",     lead.get("timing", "-"),        None),
            ("🌐 公式サイト",     website or "不明",              website),
            ("📰 情報源",         source or "不明",               source),
        ]
        for label, value, url in basic_items:
            if url and url.startswith("http"):
                rt = [
                    {"type": "text", "text": {"content": f"{label}："}},
                    {"type": "text", "text": {"content": value, "link": {"url": url}}}
                ]
            else:
                rt = make_rich_text(f"{label}：{value}")
            children.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rt}
            })

        # 市場調査セクション
        children.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": make_rich_text("📊 市場ポテンシャル調査")}
        })

        for country_label, data in [
            ("🇮🇩 インドネシア", indo),
            ("🌏 ASEAN全体", sea),
            ("🇱🇦 ラオス", laos),
        ]:
            s   = data.get("score", "-")
            sem = score_emoji(s)
            summary = data.get("summary", "-")
            opp     = data.get("opportunity", "-")
            risk    = data.get("risk", "-")

            children.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": make_rich_text(
                    f"{country_label}　{sem} {s}/10　{summary}"
                )}
            })
            children.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": make_rich_text(f"　　→ チャンス：{opp}　リスク：{risk}")}
            })

        children.append({"object": "block", "type": "divider", "divider": {}})

    # フッター
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"次回更新: {'夜20時' if SESSION == '朝' else '翌朝6時'}"
        }, "annotations": {"color": "gray"}}]}
    })

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
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
        print(f"✅ Notion保存完了: {res.json().get('url', '')}")
    else:
        print(f"❌ Notion保存失敗: {res.status_code} {res.text}")
        raise Exception("Notion API error")

# ── メイン実行 ───────────────────────────────────────
def main():
    print(f"🚀 [{NOW.strftime('%Y-%m-%d %H:%M')} JST] {SESSION}の部 開始")

    print("① 検索中（Web + ニュース + Wantedly / 九州全域）...")
    raw_data = collect_candidates()

    print("② 初回スコアリング中...")
    first_result = first_scoring(raw_data)

    print("③ クリティカル精査中...")
    reviewed = critical_review(first_result)

    print("④ 最終5社に絞り込み中...")
    final_leads = final_scoring(reviewed)
    print(f"   → {len(final_leads)}社が最終候補")

    print("⑤ 各社の市場調査中（インドネシア・ASEAN全体・ラオス）...")
    market_data = {}
    for lead in final_leads:
        company  = lead.get("company_name", "不明")
        industry = lead.get("industry", "")
        print(f"   　{company}...")
        market_data[company] = research_market(company, industry)

    print("⑥ Notionに保存中...")
    save_to_notion(final_leads, market_data)

    print("✅ 完了！")

if __name__ == "__main__":
    main()
