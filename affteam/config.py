"""設定ファイル・プロンプト・パスの共通処理。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
PLANS_DIR = ROOT / "data" / "plans"
ARTICLES_DIR = ROOT / "content" / "articles"
SNS_DIR = ROOT / "content" / "sns"
REPORTS_DIR = ROOT / "reports"
METRICS_DIR = ROOT / "data" / "metrics"
SITE_DIR = ROOT / "_site"


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_dry_run() -> bool:
    return os.getenv("AFF_DRY_RUN") == "1"


def today() -> str:
    return _dt.date.today().isoformat()


def render(name: str, **values) -> str:
    """prompts/<name>.md を読み、{{key}} を値で置き換える。"""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    for key, val in values.items():
        if not isinstance(val, str):
            val = json.dumps(val, ensure_ascii=False, indent=2)
        text = text.replace("{{" + key + "}}", val)
    return text


def program_by_id(cfg: dict, pid: str) -> dict | None:
    return next((p for p in cfg.get("programs", []) if p["id"] == pid), None)


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", s.lower()).strip("-")
    return s or "article"


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, data) -> Path:
    return write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def parse_front_matter(md: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md, re.S)
    if not m:
        return {}, md
    return yaml.safe_load(m.group(1)) or {}, m.group(2)
