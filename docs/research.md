# 調査メモ：参考にした公開ノウハウ・事例（2026-11-07 時点）

## 1. AI でのブログ・アフィリエイト自動化の実例
- ChatGPT と Claude を組み合わせ、記事作成から投稿までを半自動化した個人の事例がある → **発散（ChatGPT）と収束（Claude）の分担** として取り入れた
  - https://library.libecity.com/articles/01KP97FJ91EMXT1FKR1KGP80XJ
- Claude Code と対話しながら記事を仕上げる、成果データを取り込んで改善する運用例 → `@claude` コメント運用と週次分析に反映
  - https://library.libecity.com/articles/01KVCCB20C122NMPVC1RRTBFH3
  - https://library.libecity.com/articles/01KQ1K698X615J4N2RA5XMRVRM
- キーワード選定 → 構成 → 本文 → 公開をワークフローで繋ぐ構成（Make.com + Claude API）
  - https://lilys.ai/ja/notes/ai-blog-20251211/ai-blogging-system-5k-monthly
- AI エージェントでコンテンツ作成と GitHub ワークフローを自動化する例
  - https://www.flowhunt.io/blog/ai-agents-that-blog-and-code-for-you
- 注意: 収益・効果の数値はほぼ自己申告で、検証されたものではない。GitHub Actions でアフィリエイト運用を回す具体例は少なかった

## 2. GitHub Copilot coding agent
- Issue を Copilot に割り当てると、ブランチを作ってドラフト PR を出し、終わるとレビューを依頼してくる。修正は PR に `@copilot` コメント
- 割り当ては Issue 画面・Projects・`gh issue edit`・GraphQL API から可能。Pro / Pro+ / Business / Enterprise プランで利用可
  - https://docs.github.com/en/copilot/using-github-copilot/coding-agent/using-copilot-to-work-on-an-issue
  - https://github.blog/ai-and-ml/github-copilot/assigning-and-completing-issues-with-coding-agent-in-github-copilot/
  - https://code.visualstudio.com/docs/copilot/copilot-coding-agent

## 3. ステマ規制（景品表示法）
- 2023-10-01 からステルスマーケティングが景品表示法の不当表示に指定。違反は措置命令の対象
- 判断軸は「事業者が表示内容に関与しているか」。アフィリエイトは広告主の関与があるため **PR 表記が必要** と考えて全ページ・全投稿に自動付与する設計にした
- 執行例: 割引と引き換えに口コミを依頼したクリニック、LP に PR 表記のない SNS 投稿を載せた事例
  - https://www.fujisan.co.jp/guidance/guideline/stealth_marketing_regulation
  - https://s--line.co.jp/kigyo-sns-stealth-marketing-kisei/
  - https://www.commercepick.com/archives/42218
- 上記は二次情報。正式な基準は消費者庁の運用基準・Q&A で確認すること
