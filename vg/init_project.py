from __future__ import annotations

import json
from pathlib import Path


def init_project(slug: str) -> Path:
    root = Path("projects") / slug
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "script" / "segments").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "images").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "slides").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "bgm").mkdir(parents=True, exist_ok=True)

    project_json = root / "project.json"
    if not project_json.exists():
        project_json.write_text(
            json.dumps(
                {
                    "slug": slug,
                    "title": slug,
                    "tts": {
                        "provider": "voicevox",
                        "base_url": "http://localhost:50021",
                        "speaker": 1,
                    },
                    "video": {
                        "long": {"width": 1920, "height": 1080, "fps": 30},
                        "shorts": {"width": 1080, "height": 1920, "fps": 30},
                    },
                    "shorts_layout": {
                        "mode": "blur_bg_foreground",
                        "caption_height_ratio": 0.28,
                        "caption_box_alpha": 0.35
                    },
                    "shorts": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    article = root / "source" / "article.md"
    if not article.exists():
        article.write_text(
            "# タイトル\n\n"
            "ここに記事本文を貼ります。\n\n"
            "## セクション1\n\n"
            "読み上げたい文章を書きます。\n",
            encoding="utf-8",
        )

    return root
