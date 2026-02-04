from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .audio import concat_wavs, read_wav_info
from .project import load_project


@dataclass(frozen=True)
class TimelineItem:
    id: str
    title: str
    start: float
    end: float
    wav_path: str
    text_path: str


def build_timeline(project_dir: Path, concat_wav: bool) -> None:
    project = load_project(project_dir)

    segments_json = project.path("script", "segments.json")
    if not segments_json.exists():
        raise FileNotFoundError(f"segments.json not found: {segments_json}")
    segments = json.loads(segments_json.read_text(encoding="utf-8"))

    items: list[TimelineItem] = []
    t = 0.0
    wavs: list[Path] = []

    for seg in segments:
        seg_id = seg["id"]
        title = seg.get("title") or seg_id
        wav_path = project.path("audio", f"{seg_id}.wav")
        if not wav_path.exists():
            raise FileNotFoundError(f"wav not found: {wav_path} (run: python -m vg tts {project.root})")
        info = read_wav_info(wav_path)
        start = t
        end = t + info.duration_sec
        items.append(
            TimelineItem(
                id=seg_id,
                title=title,
                start=round(start, 3),
                end=round(end, 3),
                wav_path=f"audio/{seg_id}.wav",
                text_path=seg["text_path"],
            )
        )
        t = end
        wavs.append(wav_path)

    out = {
        "master": {
            "duration_sec": round(t, 3),
        },
        "items": [item.__dict__ for item in items],
    }

    project.path("script").mkdir(parents=True, exist_ok=True)
    project.path("script", "timeline.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if concat_wav:
        concat_wavs(wavs, project.path("export", "master.wav"))

