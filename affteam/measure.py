"""⑥ 効果測定（週次）: GA4・Search Console・A8 を同じ期間で集計し、ファネルと改善候補を出す。

出力: reports/weekly_日付.md、reports/funnel_日付.json、（データが十分なときのみ）reports/latest_insights.json
A8 の成果は data/metrics/asp/*.csv（date,program_id,slug,clicks,conversions,revenue）を置いた場合のみ集計。
置いていなければ「未取得」と表示する（0円とはみなさない）。
"""
from __future__ import annotations

import csv
import json

from . import gh
from .config import METRICS_DIR, REPORTS_DIR, is_dry_run, load_config, render, today, write_json, write_text
from .llm import claude, extract_json


def _read(folder: str) -> list[dict]:
    rows = []
    base = METRICS_DIR / "sample" if is_dry_run() else METRICS_DIR  # ドライランはサンプルCSVを使う
    for f in sorted((base / folder).glob("*.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fp:
            rows += list(csv.DictReader(fp))
    return rows


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "") or 0)
    except ValueError:
        return 0.0


def run() -> dict:
    """週次の効果測定。数字の集計・改善候補は API を使わずに出す。
    Claude は、改善候補が出たとき（＝判断に足るデータがあるとき）だけ 1 回呼び、企画向けの学びをまとめる。"""
    from . import funnel, metrics

    d = today()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    snap = metrics.snapshot(7)
    f = funnel.build(snap)
    cands = funnel.candidates(f)
    write_json(REPORTS_DIR / f"funnel_{d}.json", {**f, "candidates": cands})

    insights = []
    if cands and not is_dry_run():
        result = extract_json(claude(
            render("system_claude"), render("analyze", metrics=f, goal=cands), effort="medium",
            stub=json.dumps({"summary_md": "", "insights": []}, ensure_ascii=False)))
        insights = result.get("insights", [])[:5]
    from . import apicost
    cost = apicost.collect(f["period"]["start"], f["period"]["end"]) if not is_dry_run() else {"status": "未取得（ドライラン）"}
    write_json(REPORTS_DIR / f"apicost_{d}.json", cost)
    learn = ("\n## 学び（Claude）\n" + "\n".join(f"- {i}" for i in insights) + "\n") if insights else ""
    write_text(REPORTS_DIR / f"weekly_{d}.md", f"# 週次レポート {d}\n\n" + funnel.markdown(f, cands) + "\n"
               + apicost.markdown(cost, f["period"]) + learn)
    if insights:
        write_json(REPORTS_DIR / "latest_insights.json", {"date": d, "insights": insights})

    # 改善候補を Issue にする（同じ記事・同じ種類の Issue が開いていれば作らない）
    open_titles = gh.open_issue_titles()
    made = 0
    for c in cands:
        if c["title"] in open_titles:
            continue
        gh.create_issue(c["title"], c["body"] + f"\n\n（{d} の週次レポートより）", ["kaizen"])
        made += 1
    print(f"[効果測定] reports/weekly_{d}.md ／ 取得状況 {f['sources']} ／ 改善候補 {len(cands)}件（新規起票 {made}件）")
    return f
