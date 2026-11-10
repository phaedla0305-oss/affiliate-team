"""定時の自動企画を実行するかを判定する（config.yaml の schedule）。

- pause_until より前：定時実行は止める（手動実行は動く）
- accelerate_from より前：月曜のみ実行
- accelerate_from 以降：月曜と木曜に実行。調査（Web検索）は月曜のみ
"""
from __future__ import annotations

import datetime as dt
import os

from .config import load_config


def decide(event: str, now: dt.datetime | None = None) -> dict:
    now = now or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9))  # 日本時間
    today, wd = now.date().isoformat(), now.weekday()  # 月=0, 木=3
    s = load_config().get("schedule", {})
    if event != "schedule":
        return {"run": True, "research": True, "reason": "手動実行"}
    if today < s.get("pause_until", "0000"):
        return {"run": False, "research": False, "reason": f"{s['pause_until']} まで定時の自動企画は休止中（API費用を抑える期間）"}
    if today < s.get("accelerate_from", "9999"):
        return {"run": wd == 0, "research": wd == 0, "reason": "通常（月曜のみ）"}
    return {"run": wd in (0, 3), "research": wd == 0, "reason": "加速（月曜・木曜）"}


def budget_check(now: dt.datetime | None = None) -> dict:
    """当月の推定 API 費用（実行ログから集計）＋次の実行の見込み額が、月の予算を超えないか。"""
    from . import apicost
    now = now or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9))
    b = load_config().get("budget", {})
    cap, per_run = float(b.get("usd_per_month", 0) or 0), float(b.get("usd_per_plan_run", 0) or 0)
    if not cap:
        return {"ok": True, "reason": "予算上限なし"}
    month_start = now.date().replace(day=1).isoformat()
    c = apicost.collect(month_start, now.date().isoformat())
    if c.get("status") != "取得":
        # 集計できないときは安全側に倒して止める
        return {"ok": False, "reason": f"当月の API 費用を集計できないため停止（{c.get('status')}）"}
    used = c["usd_estimate_total"]
    ok = used + per_run <= cap
    return {"ok": ok, "used": used, "cap": cap,
            "reason": f"当月の推定 ${used:.2f} ＋ 今回の見込み ${per_run:.2f} {'≦' if ok else '＞'} 上限 ${cap:.2f}"}


def run() -> dict:
    d = decide(os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch"))
    if d["run"] and os.getenv("GITHUB_EVENT_NAME") == "schedule":
        bc = budget_check()
        print(f"[予算] {bc['reason']}")
        if not bc["ok"]:
            d.update(run=False, research=False, reason="月の予算上限のため停止：" + bc["reason"])
            from . import gh
            title = f"[予算] {dt.date.today():%Y-%m} の自動企画を停止しました"
            if title not in gh.open_issue_titles():
                body = bc["reason"] + "\n\n続ける場合は config.yaml の budget を見直すか、手動で「1. 企画」を実行してください。"
                gh.create_issue(title, body, ["budget"])
    print(f"[予定] 実行={d['run']} 調査={d['research']} ／ {d['reason']}")
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        run_flag = "true" if d["run"] else "false"
        research_flag = "true" if d["research"] else "false"
        with open(out, "a", encoding="utf-8") as f:
            f.write("run=" + run_flag + "\n")
            f.write("research=" + research_flag + "\n")
    return d
