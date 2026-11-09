"""② 制作: Claude が記事本文、ChatGPT が SNS 投稿と広告コピーのバリエーションを作る。"""
from __future__ import annotations

import json
from pathlib import Path

from . import gh
from .config import ARTICLES_DIR, SNS_DIR, load_config, program_by_id, render, today, write_json, write_text
from .llm import chatgpt, claude, extract_json


def _stub_article(plan: dict) -> str:
    return f"""---
title: "{plan['title']}"
description: "{plan['pain']}人に向けて、選び方のポイントを整理しました。"
slug: {plan['slug']}
date: {today()}
program_id: {plan['program_id']}
keyword: "{plan['keyword']}"
---

## この記事でわかること

{plan['persona']}の方に向けて、{plan['angle']}。

## {plan['outline'][0]}

ダイニングチェアは食事の時間を想定した作りのため、数時間続けて座る用途には向かないことがあります。

## {plan['outline'][1]}

1. 座面の高さが調整できるか
2. 背もたれの角度が変えられるか
3. ひじ掛けの高さが机と合うか
4. 座面の奥行きが体格に合うか
5. 試座・返品の条件

## {plan['outline'][3]}

公式サイトに掲載されている座面高・背もたれの調整範囲を、自分の身長と机の高さに当てはめて確認するのがおすすめです。

[[aff:{plan['program_id']}|公式サイトでサイズと調整範囲を確認する]]
"""


STUB_SNS = json.dumps({
    "x_posts": [
        "在宅ワークの椅子、ダイニングチェアのままにしていませんか？選ぶときに見るべき5つのポイントをまとめました #PR",
        "高い椅子で失敗したくない人へ。体格と作業時間から選ぶ方法を書きました #PR",
        "在宅勤務4日/週の私がチェアを買い替えて3か月使った感想 #PR",
    ],
    "ad_headlines": ["在宅ワークの椅子選び、5つのチェックポイント", "長時間作業でも疲れにくい椅子の選び方"],
}, ensure_ascii=False)


def _plan_from_issue(number: int) -> dict:
    # Issue 本文の ```json ブロック（人が編集した最新の企画データ）を読む
    return extract_json(gh.issue_body(number))


def _published() -> list[dict]:
    """内部リンク用の公開済み記事一覧（相対リンク先とタイトル）。"""
    from .config import parse_front_matter
    out = []
    for p in sorted(ARTICLES_DIR.glob("*.md")):
        meta, _ = parse_front_matter(p.read_text(encoding="utf-8"))
        out.append({"link": f"{p.stem}.html", "title": meta.get("title", p.stem)})
    return out


def run(plan_path: str | None = None, issue: int | None = None) -> Path:
    cfg = load_config()
    if issue:
        plan = _plan_from_issue(issue)
    else:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    program = program_by_id(cfg, plan["program_id"]) or {}
    if cfg.get("automation", {}).get("no_experience_claims"):
        experience_rule = "体験談・使用感・「使ってみた」系の記述は一切書かない。公式情報・仕様・一般的な選び方の解説だけで構成する"
    else:
        experience_rule = "体験に基づく記述は「個人の感想です」と添える。実際の体験がない内容を体験として書かない"

    # 1) Claude: 記事本文（企画書・案件規約・法令ルールを渡す）
    article = claude(
        render("system_claude"),
        render("article", plan=plan, program=program, site=cfg["site"],
               ng_rules=cfg["compliance"]["ng_patterns"], date=today(), experience_rule=experience_rule,
               articles=_published()),
        effort="high",
        web_search=int(cfg.get("research", {}).get("article_searches", 6)),
        stub=_stub_article(plan),
    ).strip()
    if article.startswith("```"):
        article = article.strip("`").split("\n", 1)[1]
    path = write_text(ARTICLES_DIR / f"{plan['slug']}.md", article + "\n")
    print(f"[制作] 記事: content/articles/{path.name}")

    # 2) ChatGPT: SNS投稿・広告見出しのバリエーション（A/Bテスト用）
    sns_raw = chatgpt(
        render("system_chatgpt"),
        render("sns", plan=plan, article=article[:4000], tags=cfg["compliance"]["sns_tags"]),
        stub=STUB_SNS,
    )
    sns = extract_json(sns_raw)
    sns.update({"slug": plan["slug"], "created": today()})
    write_json(SNS_DIR / f"{plan['slug']}.json", sns)
    print(f"[制作] SNS案 {len(sns.get('x_posts', []))} 件: content/sns/{plan['slug']}.json")
    return path


def _xlen(s: str) -> int:
    """X の重み付き文字数の概算（全角・CJK は2、それ以外は1）。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1 for c in s)


def sns_draft(slug: str) -> Path:
    """公開済み記事の SNS 投稿案だけを ChatGPT で作る（記事本文は変えない）。"""
    from .config import parse_front_matter

    cfg = load_config()
    md = (ARTICLES_DIR / f"{slug}.md").read_text(encoding="utf-8")
    meta, body = parse_front_matter(md)
    plan = {"slug": slug, "title": meta.get("title", slug), "keyword": meta.get("keyword", ""),
            "pain": meta.get("description", ""), "program_id": meta.get("program_id", "")}
    sns = extract_json(chatgpt(
        render("system_chatgpt"),
        render("sns", plan=plan, article=body[:4000], tags=cfg["compliance"]["sns_tags"]),
        stub=STUB_SNS,
    ))
    tags = cfg["compliance"]["sns_tags"]
    posts = [p.strip() for p in sns.get("x_posts", []) if isinstance(p, str)]
    # 規約タグがない・長すぎる案は使わない（URL は投稿時に付ける）
    posts = [p for p in posts if any(t in p for t in tags) and _xlen(p) + 24 <= 280]  # 改行1＋URL23
    if not posts:
        raise RuntimeError("条件を満たす投稿案がありませんでした（#PR 付き・URL込みで280以内）")
    out = {"x_posts": posts, "ad_headlines": sns.get("ad_headlines", []), "slug": slug, "created": today()}
    path = write_json(SNS_DIR / f"{slug}.json", out)
    print(f"[制作] SNS案 {len(posts)} 件: content/sns/{slug}.json")
    return path
