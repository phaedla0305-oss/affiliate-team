"""使い方:
  python -m affteam plan                    # ① 企画（ChatGPT→Claude→Issue起票）
  python -m affteam produce --issue 12      # ② 制作（Issue の企画データから記事とSNS案）
  python -m affteam produce --plan data/plans/xxx.json
  python -m affteam check [--slug s] [--no-ai]  # ③ 法令・規約チェック
  python -m affteam build                   # ④ サイト生成（_site/）
  python -m affteam sns                     # ⑤ SNS告知
  python -m affteam measure                 # ⑥ 効果測定と改善タスク起票
  python -m affteam all --dry-run           # 全工程をAPIなしで通しテスト
"""
from __future__ import annotations

import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(prog="affteam")
    ap.add_argument("--dry-run", action="store_true", help="APIを呼ばずスタブで動かす")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("research")
    sub.add_parser("plan")
    p = sub.add_parser("produce")
    p.add_argument("--issue", type=int)
    p.add_argument("--plan")
    c = sub.add_parser("check")
    c.add_argument("--slug", action="append")
    c.add_argument("--no-ai", action="store_true")
    g = sub.add_parser("gate")
    g.add_argument("--slug", required=True)
    sub.add_parser("build")
    sub.add_parser("sns")
    sub.add_parser("measure")
    sub.add_parser("all")
    args = ap.parse_args()
    if args.dry_run:
        os.environ["AFF_DRY_RUN"] = "1"

    from . import build, compliance, measure, plan, produce, research, sns
    from .config import PLANS_DIR, today

    if args.cmd == "research":
        research.run()
    elif args.cmd == "plan":
        plan.run()
    elif args.cmd == "produce":
        if not (args.issue or args.plan):
            ap.error("--issue か --plan を指定してください")
        produce.run(plan_path=args.plan, issue=args.issue)
    elif args.cmd == "check":
        return compliance.run(args.slug, use_ai=not args.no_ai)
    elif args.cmd == "gate":
        return 0 if compliance.gate(args.slug) else 2
    elif args.cmd == "build":
        build.run()
    elif args.cmd == "sns":
        sns.run()
    elif args.cmd == "measure":
        measure.run()
    elif args.cmd == "all":
        research.run()
        plans = plan.run()
        for pl in plans:
            produce.run(plan_path=str(PLANS_DIR / f"{today()}_{pl['slug']}.json"))
        if compliance.run([pl["slug"] for pl in plans]):
            print("[停止] 法令チェックで critical があるため公開工程に進みません")
            return 1
        for pl in plans:
            compliance.gate(pl["slug"])
        build.run()
        sns.run()
        measure.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
