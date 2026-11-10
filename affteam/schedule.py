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


def run() -> dict:
    d = decide(os.getenv("GITHUB_EVENT_NAME", "workflow_dispatch"))
    print(f"[予定] 実行={d['run']} 調査={d['research']} ／ {d['reason']}")
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        run_flag = "true" if d["run"] else "false"
        research_flag = "true" if d["research"] else "false"
        with open(out, "a", encoding="utf-8") as f:
            f.write("run=" + run_flag + "\n")
            f.write("research=" + research_flag + "\n")
    return d
