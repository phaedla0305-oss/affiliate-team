"""⑥ 効果測定: アクセス（GA4）と成果（ASP）の CSV を突き合わせ、Claude が分析して次の打ち手を出す。

入力（どちらも各サービスの管理画面から CSV エクスポートして置く）:
  data/metrics/ga/*.csv  … date,slug,pageviews,affiliate_clicks
  data/metrics/asp/*.csv … date,program_id,slug,clicks,conversions,revenue
                           （ASP がサブID/記事別に出せない場合 slug は空欄でOK → 案件単位で集計）
出力:
  reports/metrics_日付.csv, reports/weekly_日付.md, reports/latest_insights.json（次回の企画に渡る）
  GitHub Issue: kaizen（記事改善） / implement（サイト改善 → Copilot に割り当て）
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict

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


def aggregate() -> list[dict]:
    stats: dict[str, dict] = defaultdict(lambda: {"pv": 0.0, "clicks": 0.0, "cv": 0.0, "revenue": 0.0, "program_id": ""})
    for r in _read("ga"):
        s = stats[r["slug"]]
        s["pv"] += _num(r.get("pageviews"))
        s["clicks"] += _num(r.get("affiliate_clicks"))
    for r in _read("asp"):
        key = r.get("slug") or f"(案件) {r['program_id']}"
        s = stats[key]
        s["program_id"] = r["program_id"]
        s["cv"] += _num(r.get("conversions"))
        s["revenue"] += _num(r.get("revenue"))
        if not r.get("slug"):
            s["clicks"] += _num(r.get("clicks"))
    out = []
    for slug, s in stats.items():
        out.append({
            "slug": slug, "program_id": s["program_id"], "pv": int(s["pv"]), "clicks": int(s["clicks"]),
            "ctr": round(s["clicks"] / s["pv"], 4) if s["pv"] else None,
            "cv": int(s["cv"]), "cvr": round(s["cv"] / s["clicks"], 4) if s["clicks"] else None,
            "revenue": int(s["revenue"]), "epc": round(s["revenue"] / s["clicks"], 1) if s["clicks"] else None,
        })
    return sorted(out, key=lambda x: x["revenue"], reverse=True)


def goal_status(cfg: dict) -> dict:
    """直近30日の実績から、月の収益目標に対する達成率と、必要なPVを逆算する。"""
    import datetime as _d

    goal = int(cfg.get("goal", {}).get("monthly_revenue", 0) or 0)
    since = (_d.date.today() - _d.timedelta(days=30)).isoformat()
    pv = clicks = cv = rev = 0.0
    for r in _read("ga"):
        if r.get("date", "") >= since:
            pv += _num(r.get("pageviews"))
            clicks += _num(r.get("affiliate_clicks"))
    for r in _read("asp"):
        if r.get("date", "") >= since:
            cv += _num(r.get("conversions"))
            rev += _num(r.get("revenue"))
    ctr = clicks / pv if pv else None
    epc = rev / clicks if clicks else None
    rpm = rev / pv if pv else None  # 1PVあたりの収益
    return {
        "goal": goal, "revenue_30d": int(rev), "achievement": round(rev / goal, 3) if goal else None,
        "pv_30d": int(pv), "clicks_30d": int(clicks), "cv_30d": int(cv),
        "ctr": round(ctr, 4) if ctr else None, "epc": round(epc, 1) if epc else None,
        "required_pv_at_current_rate": int(goal / rpm) if rpm else None,
    }


def _goal_md(g: dict) -> str:
    if not g.get("goal"):
        return ""
    req = f"{g['required_pv_at_current_rate']:,} PV/月" if g.get("required_pv_at_current_rate") else "算出不可（成果データ不足）"
    ach = f"{g['achievement'] * 100:.1f}%" if g.get("achievement") is not None else "-"
    return (f"\n## 月{g['goal']:,}円目標の進捗（直近30日）\n\n| 項目 | 値 |\n|---|---|\n"
            f"| 確定報酬 | {g['revenue_30d']:,}円（達成率 {ach}） |\n| PV | {g['pv_30d']:,} |\n| 広告クリック | {g['clicks_30d']:,}（CTR {g['ctr'] or '-'}） |\n"
            f"| 成果 | {g['cv_30d']:,}件（EPC {g['epc'] or '-'}円） |\n| 今の効率で目標に必要なPV | {req} |\n")


def _stub(metrics: list[dict]) -> str:
    rows = "\n".join(f"| {m['slug']} | {m['pv']} | {m['clicks']} | {m['ctr']} | {m['cv']} | {m['revenue']} |" for m in metrics)
    return json.dumps({
        "summary_md": f"## 今週のサマリー（ドライラン）\n\n| 記事 | PV | クリック | CTR | CV | 報酬 |\n|---|---|---|---|---|---|\n{rows}",
        "insights": ["選び方系の記事はCTRが高い。比較・チェックリスト型を優先する"],
        "content_actions": [{"title": "CTRの低い記事の冒頭に結論とCTAを追加", "body": "ファーストビューに結論とCTAボタンを置く"}],
        "implement_actions": [{"title": "記事下に関連記事ブロックを追加", "body": "build.py の記事テンプレートに同じ program_id の記事を最大3件表示する。\n受け入れ条件: AFF_DRY_RUN=1 python -m affteam build が成功すること"}],
    }, ensure_ascii=False)


def run() -> dict:
    cfg = load_config()
    if not is_dry_run():
        from . import ga4
        ga4.fetch()
    metrics = aggregate()
    if not metrics:
        print("[効果測定] 集計できるデータがまだありません（分析と起票はスキップ）")
        return {}
    d = today()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / f"metrics_{d}.csv", "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(metrics[0].keys()))
        w.writeheader()
        w.writerows(metrics)

    goal = goal_status(cfg)
    result = extract_json(claude(render("system_claude"), render("analyze", metrics=metrics, goal=goal), effort="high", stub=_stub(metrics)))
    write_text(REPORTS_DIR / f"weekly_{d}.md", f"# 週次レポート {d}\n{_goal_md(goal)}\n{result['summary_md']}\n\n## 学び\n" +
               "\n".join(f"- {i}" for i in result.get("insights", [])) + "\n")
    write_json(REPORTS_DIR / "latest_insights.json", {"date": d, "insights": result.get("insights", [])})

    for a in result.get("content_actions", []):
        gh.create_issue(f"[改善] {a['title']}", a["body"] + f"\n\n（{d} の週次レポートより）", ["kaizen"])
    for a in result.get("implement_actions", []):
        gh.create_issue(f"[実装] {a['title']}", a["body"], ["implement"], assignee=cfg["github"].get("copilot_assignee"))
    print(f"[効果測定] レポート: reports/weekly_{d}.md / 改善 {len(result.get('content_actions', []))} 件・実装 {len(result.get('implement_actions', []))} 件を起票")
    return result
