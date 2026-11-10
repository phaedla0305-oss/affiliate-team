"""工程ごとの API 利用を、GitHub Actions の実行ログ（[API] 行）から集計する（API は使わない）。

- 回数とトークンは実績（ログに記録された値）
- 金額は公開料金からの推定（実際の請求額ではない）。料金は下の PRICE で管理
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

# 推定に使う公開料金（ドル）。Claude Opus 5.5：入力$4・出力$20／100万トークン、Web検索$0.01／回
PRICE = {"in": 4 / 1e6, "out": 20 / 1e6, "search": 0.01}
STEPS = {  # ワークフロー → 工程名
    "1-plan.yml": "調査・企画", "2-produce.yml": "制作・点検", "6-measure.yml": "効果測定",
    "7-recheck.yml": "再チェック", "9-sns-draft.yml": "SNS案",
}
TOK = re.compile(r"\[API\] Claude 使用トークン: 入力 (\d+) / 出力 (\d+) / キャッシュ読込 \d+ / Web検索 (\d+)回")


def _gh(args: list[str]) -> str:
    import os
    env = dict(os.environ)
    if os.getenv("ACTIONS_READ_TOKEN"):  # 実行ログの読み取りは、読み取り専用のトークンで行う
        env["GH_TOKEN"] = os.environ["ACTIONS_READ_TOKEN"]
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8", env=env).stdout


def collect(start: str, end: str) -> dict:
    if not shutil.which("gh"):
        return {"status": "未取得（gh がない）"}
    rows = {}
    try:
        for wf, step in STEPS.items():
            runs = json.loads(_gh(["run", "list", "--workflow", wf, "--created", f"{start}..{end}",
                                   "--limit", "100", "--json", "databaseId"]) or "[]")
            r = rows.setdefault(step, {"runs": len(runs), "claude_calls": 0, "chatgpt_calls": 0,
                                       "input": 0, "output": 0, "search": 0})
            for run in runs:
                try:
                    log = _gh(["run", "view", str(run["databaseId"]), "--log"])
                except subprocess.CalledProcessError:
                    continue
                r["chatgpt_calls"] += log.count("[API] ChatGPT 呼び出し")
                for m in TOK.finditer(log):
                    r["claude_calls"] += 1
                    r["input"] += int(m.group(1))
                    r["output"] += int(m.group(2))
                    r["search"] += int(m.group(3))
        for r in rows.values():
            r["usd_estimate"] = round(r["input"] * PRICE["in"] + r["output"] * PRICE["out"] + r["search"] * PRICE["search"], 2)
        total = round(sum(r["usd_estimate"] for r in rows.values()), 2)
        return {"status": "取得", "steps": rows, "usd_estimate_total": total}
    except Exception as e:
        return {"status": f"未取得（{type(e).__name__}: {str(e)[:150]}）"}


def markdown(c: dict, period: dict) -> str:
    lines = [f"## API 利用（{period['start']}〜{period['end']}）", ""]
    if c.get("status") != "取得":
        return "\n".join(lines + [c.get("status", "未取得"), ""])
    lines += ["| 工程 | 実行回数 | Claude 呼び出し | ChatGPT 呼び出し | 入力トークン | 出力トークン | Web検索 | 推定額 |",
              "|---|---|---|---|---|---|---|---|"]
    for step, r in c["steps"].items():
        lines.append(f"| {step} | {r['runs']} | {r['claude_calls']} | {r['chatgpt_calls']} | {r['input']:,} | "
                     f"{r['output']:,} | {r['search']} | ${r['usd_estimate']:.2f} |")
    lines += ["", f"推定合計：${c['usd_estimate_total']:.2f}（約{round(c['usd_estimate_total'] * 150):,}円・1ドル150円）",
              "", "- 回数・トークンは実行ログの実績。金額は公開料金からの推定で、実際の請求額・残高ではない",
              "- ChatGPT の費用・X の投稿料金は、ログからは算出していない", ""]
    return "\n".join(lines)
