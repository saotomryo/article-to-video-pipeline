from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .project import load_project


@dataclass(frozen=True)
class SpeakerAssignmentResult:
    updated: int
    total: int


def assign_speakers(
    project_dir: Path,
    *,
    speakers: list[int],
    mode: str = "alternate",
    only_missing: bool = True,
) -> SpeakerAssignmentResult:
    """
    Assigns VOICEVOX/VOICEBOX speaker ids into `script/segments.json`.

    Modes:
    - alternate: assigns speakers in order (cycle) across segments
    """
    if not speakers:
        raise ValueError("speakers must be non-empty")
    if mode != "alternate":
        raise ValueError(f"unsupported mode: {mode}")

    project = load_project(project_dir)
    seg_path = project.path("script", "segments.json")
    if not seg_path.exists():
        raise FileNotFoundError(f"segments.json not found: {seg_path}")

    data = json.loads(seg_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("segments.json must be a list")

    updated = 0
    total = 0
    i = 0
    for seg in data:
        if not isinstance(seg, dict):
            continue
        total += 1
        if only_missing and "speaker" in seg and seg["speaker"] not in (None, "", 0):
            continue
        seg["speaker"] = speakers[i % len(speakers)]
        i += 1
        updated += 1

    seg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return SpeakerAssignmentResult(updated=updated, total=total)

