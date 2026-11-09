"""GitHub（進行管理担当）とのやり取り。gh CLI を使う。

gh が無い・ドライラン時はコマンドを表示するだけにする。
"""
from __future__ import annotations

import json
import shutil
import subprocess

from .config import is_dry_run


def _enabled() -> bool:
    return not is_dry_run() and shutil.which("gh") is not None


def _run(args: list[str]) -> str:
    if not _enabled():
        print("[gh:dry]", " ".join(a if len(a) < 60 else a[:57] + "..." for a in args))
        return ""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def ensure_labels(labels: list[str]) -> None:
    for name in labels:
        try:
            _run(["label", "create", name, "--force"])
        except subprocess.CalledProcessError:
            pass


def create_issue(title: str, body: str, labels: list[str], assignee: str | None = None) -> str:
    ensure_labels(labels)
    args = ["issue", "create", "--title", title, "--body", body]
    for lb in labels:
        args += ["--label", lb]
    url = _run(args)
    if assignee and url:
        try:
            # Copilot coding agent に割り当てると、Copilot がブランチを切って PR を作る
            _run(["issue", "edit", url, "--add-assignee", assignee])
        except subprocess.CalledProcessError as e:
            print(f"[gh] {assignee} への割り当てに失敗（Copilot coding agent が未有効の可能性）: {e.stderr}")
    return url


def add_label(issue_url: str, label: str) -> None:
    """作成後に別操作でラベルを付ける（labeled イベントで制作ワークフローを起動するため）。"""
    ensure_labels([label])
    if issue_url or not _enabled():
        _run(["issue", "edit", issue_url or "<new-issue>", "--add-label", label])


def issue_body(number: int) -> str:
    out = _run(["issue", "view", str(number), "--json", "body"])
    return json.loads(out)["body"] if out else ""


def open_issue_titles() -> set[str]:
    out = _run(["issue", "list", "--state", "open", "--limit", "200", "--json", "title"])
    return {i["title"] for i in json.loads(out)} if out else set()


def a8_submit_notice(slug: str) -> None:
    """記事が公開されたら、A8.net の「広告掲載URL管理」への提出依頼を Issue にする（人の作業）。"""
    import re
    from .config import ARTICLES_DIR, load_config, parse_front_matter, program_by_id

    cfg = load_config()
    md = (ARTICLES_DIR / f"{slug}.md").read_text(encoding="utf-8")
    meta, body = parse_front_matter(md)
    ids = sorted(set(re.findall(r"\[\[aff:([a-zA-Z0-9_-]+)", body)))
    names = [(program_by_id(cfg, i) or {}).get("name", i) for i in ids]
    url = f"{cfg['site']['url'].rstrip('/')}/articles/{slug}.html"
    title = f"[A8提出] {meta.get('title', slug)[:40]}"
    if title in open_issue_titles():
        return
    body_md = ("記事が公開されました。A8.net の「参加中プログラム」→ 各案件の「プログラム詳細」→「広告掲載URL管理」から、次のURLを提出してください。\n\n"
               f"```\n{url}\n```\n\n提出先の案件：\n" + "\n".join(f"- [ ] {n}" for n in names) +
               "\n\n提出したら、このIssueを閉じてください。")
    create_issue(title, body_md, ["a8-url"])
