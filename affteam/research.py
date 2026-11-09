"""⓪ 市場調査: Claude が Web 検索で、話題・キーワード・競合の穴・高単価案件の候補を調べる。

結果は reports/research/ に保存し、直後の企画（plan.py）が読み込む。
新しい案件の候補は、ASP での提携申請が必要なので Issue（label: program）であなたに知らせる。
"""
from __future__ import annotations

import json

from . import gh
from .config import ARTICLES_DIR, REPORTS_DIR, load_config, parse_front_matter, render, today, write_json, write_text
from .llm import claude, extract_json

LATEST = REPORTS_DIR / "research" / "latest.json"

STUB = json.dumps({
    "summary_md": "## 今週の調査（ドライラン）\n- 年末年始は海外・帰省先からのリモートワーク需要が高まる",
    "keywords": [{"keyword": "海外 リモートワーク 日本のサービス 使えない", "intent": "解決策を探す", "angle": "国別の注意点と固定IPの使いどころ", "program_id": "myip", "priority": 1}],
    "competitor_gaps": ["上位記事は会社員向けで、フリーランスのIP制限対応に触れていない"],
    "title_patterns": ["【チェックリスト】〜する前に確認したい○つのこと"],
    "program_suggestions": [{"category": "オンライン英会話", "asp": "A8.net", "reason": "海外案件を受けたい在宅ワーカーに合う", "reward_hint": "無料体験申込で数百〜数千円（要確認）"}],
    "site_improvements": ["記事冒頭に目次を置く"],
}, ensure_ascii=False)


def _articles() -> list[dict]:
    out = []
    for p in sorted(ARTICLES_DIR.glob("*.md")):
        meta, _ = parse_front_matter(p.read_text(encoding="utf-8"))
        out.append({"title": meta.get("title", p.stem), "keyword": meta.get("keyword", "")})
    return out


def latest() -> dict:
    return json.loads(LATEST.read_text(encoding="utf-8")) if LATEST.exists() else {}


def run() -> dict:
    cfg = load_config()
    insights_path = REPORTS_DIR / "latest_insights.json"
    insights = insights_path.read_text(encoding="utf-8") if insights_path.exists() else "（まだなし）"
    programs = [{k: p[k] for k in ("id", "name", "reward", "rules")} for p in cfg["programs"]]
    result = extract_json(claude(
        render("system_claude"),
        render("research", site=cfg["site"]["name"], niche=cfg["niche"], target=cfg["target"],
               programs=programs, articles=_articles(), insights=insights),
        effort="high",
        web_search=int(cfg.get("research", {}).get("max_searches", 8)),
        stub=STUB,
    ))
    result["date"] = today()
    write_json(LATEST, result)
    write_text(REPORTS_DIR / "research" / f"research_{today()}.md", f"# マーケットリサーチ {today()}\n\n{result.get('summary_md', '')}\n")
    print(f"[調査] キーワード候補 {len(result.get('keywords', []))} 件 / 案件候補 {len(result.get('program_suggestions', []))} 件")

    sugg = result.get("program_suggestions", [])
    if sugg and any(x.startswith("[案件候補]") for x in gh.open_issue_titles()):
        print("[調査] 案件候補の Issue が未対応のまま開いているため、新しい Issue は作りません（候補は reports/research/latest.json に保存）")
        sugg = []
    if sugg:
        body = "週次リサーチで、読者に合いそうな高単価案件の種類が見つかりました。ASP で探して提携できたら、案件情報をチャットで送ってください。\n\n"
        body += "\n".join(f"- [ ] **{s['category']}**（{s.get('asp', 'ASP不明')}）: {s['reason']} ／ 報酬の目安: {s.get('reward_hint', '要確認')}" for s in sugg)
        gh.create_issue(f"[案件候補] {today()} の提携候補 {len(sugg)} 件", body, ["program"])
    return result
