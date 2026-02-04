---
name: dialog-video-ja
description: Use when the user wants to turn an explanatory article into a dialogue-style script (対話形式) and generate a dialogue video in this repo, using per-line VOICEVOX speakers via projects/{slug}/script/dialog.md and python -m vg dialog/tts/render.
metadata:
  short-description: Dialogue-style video pipeline (JP)
---

# 対話形式（2人以上）動画スキル

目的：記事を「会話（対話）形式」にして、VOICEVOX の話者を切り替えながら動画を作ります。

## 入出力

- 入力:
  - `projects/{slug}/source/article.md`（元記事）
  - `projects/{slug}/script/dialog.md`（対話台本：A: / B: 形式）
  - `projects/{slug}/project.json`（話者割り当て）
- 出力:
  - `projects/{slug}/script/segments/*.txt`
  - `projects/{slug}/script/segments.json`（各セグメントに `speaker` を付与）
  - `projects/{slug}/audio/*.wav`
  - `projects/{slug}/export/master_long.mp4`

## dialog.md の書き方（最小）

- `##` 見出しで章（画像の割り当て単位）を作る
- 各行を `A: ...` / `B: ...` のように書く（1行＝1発話）
- 1行だけ個別に話者IDを指定したい場合は `A(1): ...` のように書ける

例:

```md
# タイトル（任意）

## 導入
A: 今日は国の支出を可視化してみます。
B: どんなデータを使うの？

## 使い方
A: まずCSVをダウンロードします。
B: それをアプリにアップロードするんだね。
```

## project.json で話者IDを割り当てる

`projects/{slug}/project.json` に `dialog.speakers` を追加します（VOICEVOX の speaker id）。

```json
{
  "dialog": {
    "speakers": { "A": 1, "B": 8 }
  }
}
```

## 実行手順

1) 対話台本をコンパイル（発話ごとにセグメント化）

```
python -m vg dialog projects/{slug} --force
```

2) TTS（speaker は `segments.json` の `speaker` を優先）

```
python -m vg tts projects/{slug}
```

3) タイムライン生成 → レンダリング

```
python -m vg timeline projects/{slug} --concat-wav
python -m vg render projects/{slug} --force
```

（任意）画像/スライド割り当て:

```
python -m vg visuals projects/{slug} --force
```

## 台本（内容）生成の指針

- 片方が質問・相槌、片方が説明の役割になるようにする
- 1発話は短め（1〜2文程度）
- 記事の事実から逸脱しない（要約はOK）
