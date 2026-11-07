# Copilot への指示（実装担当）

このリポジトリはアフィリエイトサイトを AI チームで運営するためのものです。あなた（Copilot）の担当は **サイトの実装改善** と **PR レビュー** です。

## 担当範囲
- `affteam/build.py`（HTML/CSS テンプレート、リンク計測、サイトマップ）の改善
- `implement` ラベルの Issue。受け入れ条件を満たす最小の変更で PR を出す
- PR レビューでは次を確認する
  - 全ページに PR 表記（`config.yaml` の `compliance.pr_label`）が出ること
  - 広告リンクに `rel="sponsored"` が付き、`/go/` 中継ページ経由になっていること
  - 記事本文に生の広告URLが無いこと（`[[aff:ID|文言]]` 形式）
  - スマホ幅（375px）で横スクロールが出ないこと

## やってはいけないこと
- `content/articles/` の記事本文の書き換え（記事は Claude と人が担当）
- `config.yaml` の `programs[].url`（広告リンク）や `compliance` の変更
- API キーなどの秘密情報をコードに書くこと

## 確認コマンド
```bash
pip install -r requirements.txt
python -m affteam --dry-run all
python -m affteam check --no-ai
```
