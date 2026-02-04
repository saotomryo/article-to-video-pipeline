---
name: chapter-split-ja
description: Use when the user has a long plain text / docx / pptx / rough Markdown and wants an AI-assisted chapter split (見出し付け・章分割) into projects/{slug}/source/article.md suitable for the vg pipeline, then generate narration segments.
metadata:
  short-description: AI chapter split for article (JP)
---

# 章分割（AI）スキル：テキスト→記事Markdown整形

目的：見出しが不明なテキスト（txt/docx/pptx由来など）を、動画向けに **章分割されたMarkdown** に整形します。

## 入出力

- 入力:
  - `projects/{slug}/source/article.md`（取り込み直後のラフなMarkdownでもOK）
- 出力:
  - `projects/{slug}/source/article.md`（見出し付きに再構成）
  - `projects/{slug}/script/segments/*.txt`
  - `projects/{slug}/script/segments.json`

## 方針

- 事実関係は入力テキストから逸脱しない（要約OK、捏造NG）
- 見出し構成は、**読み上げと動画の流れ**を優先して整理
- 1章はだいたい 30〜90秒程度の分量を目安（長い章は分割）
- Markdownのリンク/URL/ノイズ（SNS誘導、フッター等）は必要に応じて削る

## 手順

1) 対象の `projects/{slug}/source/article.md` を読み、本文を理解する
2) 次の形式で `article.md` を作り直す（最低限）

- 先頭は `# タイトル`
- `##` 見出しで章を作る（5〜15章を目安）
- 箇条書きは必要なら残すが、後で `vg script` でテキスト化される前提

3) `vg script` を実行してセグメントを作る

```
python -m vg script projects/{slug}
```

4) セグメントを目視して、明らかに長い/短いものがあれば、`article.md` の見出しを調整して 3) をやり直す

## よくあるケース

- **docx/pptx 取り込みで見出しが弱い**：章タイトルを補って `##` を付与する
- **スライドの羅列**：スライドをまとめて章にし、導入→本論→まとめに整理する

