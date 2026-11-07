"""① 企画: ChatGPT がアイデアを広げ、Claude が絞り込んで企画書にし、GitHub Issue に起票する。"""
from __future__ import annotations

import json
import os

from . import gh
from .config import PLANS_DIR, REPORTS_DIR, load_config, render, slugify, today, write_json
from .llm import chatgpt, claude, extract_json

STUB_IDEAS = json.dumps([
    {"idea": "在宅ワークで腰がつらい人向けのチェア選び方ガイド", "program_id": "sample-chair", "keyword": "在宅ワーク 椅子 おすすめ"},
    {"idea": "カフェ作業で公衆Wi-Fiを使う人向けのVPN入門", "program_id": "sample-vpn", "keyword": "カフェ Wi-Fi 危険 VPN"},
], ensure_ascii=False)

STUB_PLANS = json.dumps([{
    "slug": "remote-work-chair-guide",
    "title": "在宅ワーク用チェアの選び方｜長時間座っても疲れにくい5つのチェックポイント",
    "keyword": "在宅ワーク 椅子 おすすめ",
    "search_intent": "比較検討（購入直前）",
    "persona": "在宅勤務4日/週、ダイニングチェアで作業していて夕方に疲れる32歳会社員",
    "pain": "長時間座ると疲れるが、高い椅子を買って失敗したくない",
    "program_id": "sample-chair",
    "angle": "価格帯別に『自分の体格と作業時間に合うか』で選ぶ方法を示す",
    "outline": ["ダイニングチェアで疲れる理由", "選ぶときの5つのチェックポイント", "価格帯別の選び方", "サンプル在宅ワークチェアの仕様をチェック", "よくある質問"],
    "cta": "体格に合うサイズか公式ページで確認する",
    "evidence_needed": ["メーカー公式の寸法・調整範囲", "使用期間と使用条件"],
    "risk_notes": ["腰痛が治る等の医療的表現は使わない"],
    "score": {"demand": 4, "monetize": 4, "competition": 3},
}], ensure_ascii=False)


def run() -> list[dict]:
    cfg = load_config()
    insights_path = REPORTS_DIR / "latest_insights.json"
    insights = insights_path.read_text(encoding="utf-8") if insights_path.exists() else "（まだ効果測定データなし）"
    programs = [{k: p[k] for k in ("id", "name", "reward", "rules")} for p in cfg["programs"]]

    # 1) ChatGPT: 発散（量を出す）
    ideas_raw = chatgpt(
        render("system_chatgpt"),
        render("brainstorm", niche=cfg["niche"], target=cfg["target"], programs=programs,
               insights=insights, n=str(cfg["plan"]["ideas_per_run"])),
        stub=STUB_IDEAS,
    )
    ideas = extract_json(ideas_raw)
    print(f"[企画] ChatGPT のアイデア {len(ideas)} 件")

    # 2) Claude: 収束（評価して企画書にする）
    plans_raw = claude(
        render("system_claude"),
        render("plan", niche=cfg["niche"], target=cfg["target"], programs=programs, ideas=ideas,
               insights=insights, n=str(cfg["plan"]["plans_per_run"])),
        effort="high",
        stub=STUB_PLANS,
    )
    plans = extract_json(plans_raw)

    # 3) 保存して GitHub Issue に起票（人が内容を確認し approved ラベルで制作へ）
    for p in plans:
        p["slug"] = slugify(p.get("slug", ""))
        path = write_json(PLANS_DIR / f"{today()}_{p['slug']}.json", p)
        body = (
            f"## 企画書\n\n- **キーワード**: {p['keyword']}\n- **ペルソナ**: {p['persona']}\n"
            f"- **悩み**: {p['pain']}\n- **切り口**: {p['angle']}\n- **案件**: `{p['program_id']}`\n"
            f"- **CTA**: {p['cta']}\n\n### 構成\n" + "\n".join(f"1. {h}" for h in p["outline"]) +
            "\n\n### 要確認\n" + "\n".join(f"- [ ] {e}" for e in p.get("evidence_needed", []) + p.get("risk_notes", [])) +
            "\n\n---\n内容を確認・修正したら **`approved` ラベル** を付けてください。制作ワークフローが動きます。\n\n"
            f"<details><summary>企画データ（制作AIが読み込みます。編集可）</summary>\n\n```json\n"
            f"{json.dumps(p, ensure_ascii=False, indent=2)}\n```\n</details>\n"
        )
        url = gh.create_issue(f"[企画] {p['title']}", body, ["kikaku"])
        auto = cfg.get("automation", {}).get("auto_approve_plans") and os.getenv("AFF_AUTO_APPROVE", "true") != "false"
        if auto:
            gh.add_label(url, "approved")  # 自動承認 → 制作ワークフローが起動
        print(f"[企画] 保存: {path.relative_to(PLANS_DIR.parent.parent)}")
    return plans
