"""③ 法令・規約チェック: 機械チェック（NG表現・PR表記・リンク形式）＋ Claude によるレビュー。

critical が1件でもあれば終了コード1（CI を失敗させ、公開を止める）。
"""
from __future__ import annotations

import json
import re

from .config import ARTICLES_DIR, REPORTS_DIR, SNS_DIR, load_config, parse_front_matter, program_by_id, render, write_text
from .llm import claude, extract_json

STUB_REVIEW = json.dumps({"verdict": "pass", "issues": []})


def check_article(slug: str, cfg: dict, use_ai: bool = True) -> list[dict]:
    md = (ARTICLES_DIR / f"{slug}.md").read_text(encoding="utf-8")
    meta, body = parse_front_matter(md)
    issues: list[dict] = []

    for rule in cfg["compliance"]["ng_patterns"]:
        for m in re.finditer(rule["pattern"], body):
            issues.append({"severity": rule["level"], "quote": m.group(0), "reason": rule["reason"], "where": "記事"})

    if not meta.get("program_id") or not program_by_id(cfg, meta["program_id"]):
        issues.append({"severity": "critical", "quote": str(meta.get("program_id")), "reason": "config.yaml に無い案件ID", "where": "front matter"})
    if re.search(r"https?://\S*(a8\.net|moshimo|valuecommerce|afb|accesstrade)", body):
        issues.append({"severity": "critical", "quote": "生の広告URL", "reason": "広告リンクは [[aff:案件ID|文言]] 形式で書く（計測と rel=sponsored のため）", "where": "記事"})
    if "[[aff:" not in body:
        issues.append({"severity": "warn", "quote": "", "reason": "広告リンクが1つもない", "where": "記事"})
    for m in re.finditer(r"<!--\s*要確認[:：]?(.*?)-->", body, re.S):
        issues.append({"severity": "warn", "quote": m.group(1).strip()[:40], "reason": "人による事実確認が必要", "where": "記事"})
    if cfg.get("automation", {}).get("no_experience_claims"):
        # 体験談の言い回しだけを拾う（「実際に使うツール」のような普通の表現は対象外）
        for m in re.finditer(r"(使ってみ(た|まし)|使った感想|実際に使って(み|い)|個人の感想|愛用して)", body):
            issues.append({"severity": "warn", "quote": m.group(0), "reason": "自動公開モードでは体験談を書かない設定", "where": "記事"})

    sns_path = SNS_DIR / f"{slug}.json"
    if sns_path.exists():
        sns = json.loads(sns_path.read_text(encoding="utf-8"))
        for post in sns.get("x_posts", []):
            if not any(t in post for t in cfg["compliance"]["sns_tags"]):
                issues.append({"severity": "critical", "quote": post[:40], "reason": "SNS投稿に #PR / #広告 がない（ステマ規制）", "where": "SNS"})

    if use_ai:
        review = extract_json(claude(
            render("system_claude"),
            render("review", article=md, program=program_by_id(cfg, meta.get("program_id", "")) or {},
                   pr_label=cfg["compliance"]["pr_label"]),
            effort="high",
            stub=STUB_REVIEW,
        ))
        for it in review.get("issues", []):
            it.setdefault("where", "記事（AIレビュー）")
            issues.append(it)
    return issues


def run(slugs: list[str] | None = None, use_ai: bool = True) -> int:
    cfg = load_config()
    slugs = slugs or [p.stem for p in sorted(ARTICLES_DIR.glob("*.md"))]
    worst = 0
    for slug in slugs:
        issues = check_article(slug, cfg, use_ai)
        crit = [i for i in issues if i.get("severity") == "critical"]
        lines = [f"# 法令・規約チェック: {slug}", "", f"判定: **{'NG（要修正）' if crit else 'OK'}**", ""]
        lines += [f"- [{i['severity']}] {i['where']}「{i.get('quote', '')}」: {i['reason']}"
                  + (f" → {i['suggestion']}" if i.get("suggestion") else "") for i in issues] or ["- 指摘なし"]
        write_text(REPORTS_DIR / "compliance" / f"{slug}.md", "\n".join(lines) + "\n")
        write_text(REPORTS_DIR / "compliance" / f"{slug}.json", json.dumps(issues, ensure_ascii=False, indent=2))
        print(f"[チェック] {slug}: critical {len(crit)} / 全 {len(issues)} 件")
        if crit:
            worst = 1
    return worst


def gate(slug: str) -> bool:
    """自動公開してよいか。直前の check の結果で、指摘が1件も無いときだけ True。"""
    cfg = load_config()
    if not cfg.get("automation", {}).get("auto_merge"):
        print(f"[公開判定] {slug}: auto_merge が無効 → 人の確認待ち")
        return False
    path = REPORTS_DIR / "compliance" / f"{slug}.json"
    if not path.exists():
        print(f"[公開判定] {slug}: チェック結果が無い → 人の確認待ち")
        return False
    issues = json.loads(path.read_text(encoding="utf-8"))
    ok = not issues
    print(f"[公開判定] {slug}: {'自動公開OK' if ok else f'指摘 {len(issues)} 件 → 人の確認待ち'}")
    return ok
