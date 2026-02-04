---
name: reading-script-ja
description: Use when the user wants to create/clean a Japanese narration script (読み上げ台本) from an article Markdown in this repo (projects/{slug}/source/article.md), ready for VOICEBOX/VOICEVOX TTS. Produces reusable script segments under projects/{slug}/script/segments and updates segments.json (optionally adds storyboard notes).
metadata:
  short-description: Create Japanese narration script segments
---

# 読み上げ台本（日本語）作成スキル

このリポジトリの「記事→台本→TTS→動画」パイプラインで、**VOICEBOX（VOICEVOX互換API）に流すための読み上げ台本**を作るための手順です。

## 入出力（この形式を守る）

- 入力:
  - `projects/{slug}/source/article.md`（記事のMarkdown）
- 出力:
  - `projects/{slug}/script/segments/*.txt`（TTS用の読み上げ文。Markdown禁止）
  - `projects/{slug}/script/segments.json`（セグメント一覧）
  - （任意）`projects/{slug}/storyboard/storyboard.md`（画面指示。TTSに混ぜない）

## ワークフロー（最短）

1) ベース生成（機械的分割）
- `python -m vg script projects/{slug}` を実行して `script/segments` を作る

2) 台本に「読み上げ向けの修正」を入れる（人間が聞きやすい形）
- 各 `script/segments/*.txt` を編集して、下の「整形ルール」に従い読み上げ文にする
- 事実関係は記事から逸脱しない（要約はOK、捏造NG）

3) 長さチェック（TTS/編集しやすさ）
- 1セグメントは原則 **10〜25秒**（長い場合はセグメント分割）
- セグメント間は自然な接続（「次に〜」「ここからは〜」）を入れてよい

4) 画面指示（任意）
- 読み上げテキストに画面指示を混ぜない（TTSに読まれる）
- 代わりに `projects/{slug}/storyboard/storyboard.md` を作り、`segment_id` ごとに表示素材を指定する

## 整形ルール（TTS向け）

### 禁止/避ける

- Markdown記法（見出し`#`、リンク`[]()`、箇条書き`-`など）をそのまま残さない
- URLを読み上げない（「リンクは概要欄に置きます」で置換）
- 「copy」「ダウンロード」など記事下部のノイズは削除
- かっこ書きが多い文は崩す（`（※...）` は必要なら口語に言い換え）

### 推奨

- です/ます調（統一）
- 1文を短く（長いと聞き取りづらい）
- 数字や略語は読みやすく（例: “2026年”はOK、英字略語は必要なら補足）
- 固有名詞は表記を揺らさない（同じ呼び方に統一）

### 箇条書きの扱い

- 箇条書きは「まず〜。次に〜。最後に〜。」のように読み上げ文へ変換

## 出力の品質チェック（最低限）

- `script/segments/*.txt` を目視して、**読み上げて自然**か
- 1セグメントが長すぎないか（必要なら分割）
- 余計な記号やURLが残っていないか

## 具体例（変換の方向性）

- 変換前: `アプリケーション https://example.com`
- 変換後: `アプリケーションは概要欄にリンクを置いておきます。`

