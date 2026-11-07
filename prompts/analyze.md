アフィリエイトサイトの記事別の成果データを分析し、次の打ち手を決めてください。

# 指標の見方
- pv: 記事の閲覧数 / clicks: 広告リンクのクリック数 / ctr = clicks / pv
- cv: 成果件数 / cvr = cv / clicks / revenue: 確定報酬 / epc = revenue / clicks
- 典型的な打ち手: PVはあるがCTRが低い → 導線・CTA位置の改善 / CTRは高いがCVRが低い → 案件の見直し・事前説明の追加 / 全体にPVが少ない → 関連キーワードの記事追加・SNS告知

# データ
{{metrics}}

# 出力形式（JSON のみ）
{
  "summary_md": "週次レポート本文（Markdown、見出し・表を含めてよい）",
  "insights": ["次の企画に活かす学び（1行ずつ）"],
  "content_actions": [{"title": "記事の改善・新規企画タスク", "body": "具体的な内容"}],
  "implement_actions": [{"title": "サイトの実装改善タスク（Copilot に割り当て）", "body": "受け入れ条件つきで具体的に"}]
}
