---
name: import-url-ja
description: Use when the user wants to fetch a specified article URL, convert it to Markdown, and create a new video project under projects/{slug} (including optional image download) in this repo.
metadata:
  short-description: Import URL to project (JP)
---

# URL→Markdown 取り込み＋案件作成スキル（日本語）

指定したURLの記事を取得して、`projects/{slug}` の案件ディレクトリを作るところまでを行います。

## 入出力

- 入力:
  - 記事URL（http/https）
  - `slug`（案件ディレクトリ名。省略時は推測）
- 出力:
  - `projects/{slug}/project.json`
  - `projects/{slug}/source/article.md`
  - `projects/{slug}/source/article.html`
  - （任意）`projects/{slug}/assets/images/article/*`

## 依頼時に確認すること（最小）

1) 取り込みたいURLはどれ？
2) `slug` は何にする？（なければ候補を提案して確認する）
3) 画像もローカルDLする？（必要なら `--fetch-images --rewrite-images`）

## 実行（案件作成まで）

### A) まず案件を作って記事を取り込む

```
python -m vg import-url "<URL>" --slug <slug>
```

既に `projects/{slug}/source/article.md` がある場合は上書きしないので、必要なら `--force` を使う。

### B) 記事内画像も落とす（任意）

```
python -m vg import-url "<URL>" --slug <slug> --fetch-images --rewrite-images
```

## 取り込み後の確認ポイント

- `projects/{slug}/source/article.md` がMarkdownになっている（見出し/段落/リンク/画像）
- 余計なナビ/フッターが混ざっていたら、手で削って整形する
- 動的ページ/有料記事で本文が取れない場合は、`article.md` に手動で貼り付けて進める

