---
name: speaker-assign-ja
description: Use when the user wants to assign different VOICEVOX/VOICEBOX speakers to segments (speaker id per segment) either automatically (content/role-based) or manually, for dialogue or narration projects in this repo.
metadata:
  short-description: Assign VOICEVOX/VOICEBOX speakers (JP)
---

# 話者割り当て（VOICEVOX / VOICEBOX）スキル

目的：TTS生成時に **セグメントごとに話者（speaker id）** を変えられるようにします。

このリポジトリでは `projects/{slug}/script/segments.json` の各要素に `speaker` を入れると、`python -m vg tts` がそれを優先します。

## 方式（おすすめ順）

### A) 対話台本（dialog.md）で指定（おすすめ）

`projects/{slug}/script/dialog.md` の各行で、話者IDを直接指定できます。

例:

```md
## 導入
A(1): 今日はここから始めます。
B(8): なるほど、聞いていくね。
```

または `project.json` にまとめて割り当ててもOKです。

```json
{
  "dialog": { "speakers": { "A": 1, "B": 8 } }
}
```

実行:

```
python -m vg dialog projects/{slug} --force
python -m vg tts projects/{slug}
```

### B) 既存セグメント（segments.json）に一括で割り当て

台本が対話形式でなくても、セグメントへ機械的に話者を割り当てられます（例：交互にする）。

```
python -m vg assign-speakers projects/{slug} --speakers 1,8
python -m vg tts projects/{slug} --force
```

既に speaker が入っているセグメントも上書きする場合:

```
python -m vg assign-speakers projects/{slug} --speakers 1,8 --all
```

### C) 内容に応じて割り当て（AI）

以下の方針で、`segments.json` への `speaker` 付与を提案・反映する。

- 説明役（落ち着いた声）と質問役（相槌・確認）を分ける
- 「結論/まとめ」は説明役に寄せる
- 1セグメント内で話者が混ざる場合は、セグメントを分割する（`dialog.md` 方式へ）

## 注意

- speaker id は VOICEVOX/VOICEBOX のエンジン側の定義に依存します（環境で番号が違う可能性があります）。
- `tts` の `--speaker` は「デフォルト話者」の上書きで、`segments.json` の `speaker` があればそちらが優先されます。

