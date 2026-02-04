---
name: segment-visuals-ja
description: Use when the user wants to add slides and images into the video by assigning per-segment visuals: use full images where available, and show generated slides only for segments with no images.
metadata:
  short-description: Assign visuals per segment (JP)
---

# セグメント画像割り当て（画像優先・無い箇所だけスライド）スキル

目的：動画レンダリングで使う画像を `assets/images/{segment_id}.*` に揃える。

- **画像があるセグメント**：その画像だけを表示（スライドは作らない）
- **画像が無いセグメント**：簡単なスライド画像（PNG）を生成して表示

## 前提（このリポジトリの仕様）

- `python -m vg render projects/{slug}` は `projects/{slug}/assets/images/{segment_id}.(png|jpg|jpeg)` があるとそれを使う
- `projects/{slug}/assets/images/article/` は記事からダウンロードした画像置き場（`fetch-images`）
- `projects/{slug}/source/article.html` がある場合、記事内の `<figure>`（画像の登場位置）を優先してセグメントへ割り当てる

## 手順

1) （未実施なら）記事内画像をダウンロード

```
python -m vg fetch-images projects/{slug} --md source/article.md --out-dir assets/images/article --rewrite
```

（任意）先頭画像（アイキャッチ）を差し替える場合は、次のパスに保存しておく：

- `projects/{slug}/assets/images/article/eyecatch_override.png`

2) セグメントごとの表示画像を割り当てる（画像が無い箇所だけスライド生成）

```
python -m vg visuals projects/{slug} --force
```

生成物：
- `projects/{slug}/assets/images/{segment_id}.png` など（レンダリング入力）
- `projects/{slug}/assets/images/assignments.json`（割り当てログ）

3) 反映して長尺を再生成

```
python -m vg render projects/{slug} --force
```

## 注意

- 画像の割り当てが意図と違う場合は `assets/images/assignments.json` を見て、必要なら該当 `assets/images/{segment_id}.*` を手で差し替える。
  - 記事内の画像位置に合わせたい場合は、`source/article.html` が存在する状態で実行する。
