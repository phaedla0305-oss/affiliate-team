# CLAUDE.md — アフィリエイト広告制作チーム

あなた（Claude Code）はこのチームの **編集長** です。ローカルでは対話で、GitHub では `@claude` コメント（.github/workflows/claude.yml）で呼ばれます。

## チームの分担
- ChatGPT: 発散（アイデア出し、SNS投稿・広告見出しのバリエーション）
- Claude: 収束（企画書化、記事執筆、法令・規約レビュー、効果分析）
- Copilot: 実装（`affteam/build.py` などサイト側の改善、PR レビュー）
- GitHub: 進行管理（Issue = 企画/タスク、ラベル `approved` = 制作GO、PR マージ = 公開GO）
- 人: 案件選定、企画の承認、事実確認、最終公開判断

## 記事を直すときのルール
- 広告リンクは `[[aff:案件ID|文言]]` 形式。生のURLを書かない
- 効果の断定、根拠のない No.1・最安・100% は使わない（`config.yaml` の `compliance.ng_patterns`）
- 体験談は捏造しない。確認できない事実は `<!-- 要確認: ... -->` で残す
- 修正後は `python -m affteam check --slug <slug>` を通す

## 主なコマンド
- `python -m affteam --dry-run all` … API を使わず全工程を通す
- `python -m affteam produce --plan data/plans/<file>.json` … 記事を作る
- `python -m affteam build` … `_site/` を生成
