"""AIメンバーの呼び出し口。

- ChatGPT (OpenAI)  : 発散担当。アイデア出し・SNS投稿・広告コピーのバリエーション
- Claude (Anthropic): 収束担当。企画書化・記事執筆・法令チェック・効果分析

AFF_DRY_RUN=1 のときは API を呼ばず、各モジュールが渡すスタブを返す（動作確認用）。
"""
from __future__ import annotations

import json
import os
import re

from .config import is_dry_run

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

# AI 同士のプロンプトは各 AI の判断で自由に送るが、次の情報が混ざっていたら送信前に止める
SENSITIVE = {
    "APIキー・トークン": r"(sk-ant-[\w-]{10,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16})",
    "メールアドレス": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "電話番号": r"(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)",
    "口座情報": r"(口座番号|支店番号|口座名義|普通預金|当座預金)",
    "カード番号": r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)",
    "マイナンバー・本人確認書類": r"(マイナンバー|個人番号|運転免許証番号|パスポート番号)",
}


class SensitiveDataError(RuntimeError):
    """送信を止めた。中身は表示せず種類だけ伝える（ログからの漏洩を防ぐ）。"""


def guard(*texts: str) -> None:
    from .config import load_config

    if not load_config().get("automation", {}).get("block_sensitive_in_prompts", True):
        return
    hits = [name for name, pat in SENSITIVE.items() for t in texts if re.search(pat, t or "")]
    if hits:
        raise SensitiveDataError(
            f"AIへの送信を停止しました（検出: {', '.join(sorted(set(hits)))}）。"
            "個人情報・秘密情報の可能性があるため、内容を確認してから再実行してください。"
        )


def claude(system: str, prompt: str, *, effort: str = "high", stub: str = "") -> str:
    guard(system, prompt)
    if is_dry_run():
        return stub
    import anthropic

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境変数から読む
    # 長文生成になるのでストリーミング。拒否時は fallbacks="default" で自動的に別モデルへ回す
    with client.beta.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude が応答を拒否しました: {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude の出力が上限で途切れました")
    return "".join(b.text for b in resp.content if b.type == "text")


def chatgpt(system: str, prompt: str, *, stub: str = "") -> str:
    guard(system, prompt)
    if is_dry_run():
        return stub
    from openai import OpenAI

    client = OpenAI()  # OPENAI_API_KEY を環境変数から読む
    resp = client.responses.create(model=OPENAI_MODEL, instructions=system, input=prompt)
    return resp.output_text


def extract_json(text: str):
    """応答から最初の JSON（```json ブロック優先）を取り出す。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = m.group(1) if m else text
    start = min([i for i in (body.find("{"), body.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError(f"JSON が見つかりません: {text[:200]}")
    return json.JSONDecoder().raw_decode(body[start:])[0]
