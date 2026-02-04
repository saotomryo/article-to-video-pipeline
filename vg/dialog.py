from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .project import load_project


@dataclass(frozen=True)
class DialogLine:
    speaker_key: str
    speaker_id: int | None
    text: str
    section_title: str


_heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_dialog_re = re.compile(r"^([A-Za-z][A-Za-z0-9_-]{0,15})(?:\((\d{1,5})\))?\s*:\s*(.+?)\s*$")


def build_dialog_segments(project_dir: Path, *, source_relpath: str = "script/dialog.md", force: bool = False) -> None:
    """
    Compiles `script/dialog.md` (A: ..., B: ...) into `script/segments/*.txt` + `script/segments.json`.

    - Each dialog line becomes one TTS segment.
    - Segment `title` is the nearest preceding section heading (## ...), used for image selection.
    - Segment item includes optional `speaker` (VOICEVOX speaker id).
    """
    project = load_project(project_dir)
    dialog_path = project.path(source_relpath)
    if not dialog_path.exists():
        raise FileNotFoundError(f"dialog not found: {dialog_path}")

    dialog_md = dialog_path.read_text(encoding="utf-8", errors="replace")
    lines = _parse_dialog(dialog_md)
    if not lines:
        raise ValueError(f"no dialog lines found in: {dialog_path}")

    speaker_map = _load_speaker_map(project)

    seg_dir = project.path("script", "segments")
    if force and seg_dir.exists():
        for p in seg_dir.glob("*.txt"):
            p.unlink()
    seg_dir.mkdir(parents=True, exist_ok=True)

    index: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        seg_id = f"{idx:04d}_{_slugify(line.speaker_key)}"
        txt_path = seg_dir / f"{seg_id}.txt"
        txt_path.write_text(line.text.strip() + "\n", encoding="utf-8")

        item: dict = {
            "id": seg_id,
            "title": line.section_title or "intro",
            "text_path": f"script/segments/{seg_id}.txt",
        }
        speaker = line.speaker_id if line.speaker_id is not None else speaker_map.get(line.speaker_key)
        if speaker is not None:
            item["speaker"] = speaker
        index.append(item)

    (project.path("script") / "segments.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_dialog(markdown: str) -> list[DialogLine]:
    out: list[DialogLine] = []
    cur_section = "intro"

    in_frontmatter = False
    frontmatter_done = False

    for raw in markdown.splitlines():
        line = raw.rstrip("\n")

        if not frontmatter_done and line.strip() == "---":
            in_frontmatter = not in_frontmatter
            if not in_frontmatter:
                frontmatter_done = True
            continue
        if in_frontmatter:
            continue

        if not line.strip():
            continue
        if line.lstrip().startswith(("<!--", "//")):
            continue

        m = _heading_re.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            # Use H2+ as section grouping; ignore H1.
            if level >= 2 and title:
                cur_section = title
            continue

        m = _dialog_re.match(line)
        if not m:
            continue
        speaker_key = m.group(1).strip()
        speaker_id = int(m.group(2)) if m.group(2) else None
        text = m.group(3).strip()
        if text:
            out.append(DialogLine(speaker_key=speaker_key, speaker_id=speaker_id, text=text, section_title=cur_section))

    return out


def _load_speaker_map(project) -> dict[str, int]:
    # project.json:
    # - "dialog": {"speakers": {"A": 1, "B": 8}}
    # - fallback: tts.speaker
    cfg = project.config or {}
    dialog = cfg.get("dialog") if isinstance(cfg, dict) else None
    speakers = dialog.get("speakers") if isinstance(dialog, dict) else None
    out: dict[str, int] = {}
    if isinstance(speakers, dict):
        for k, v in speakers.items():
            if isinstance(k, str) and isinstance(v, int):
                out[k] = v
            if isinstance(k, str) and isinstance(v, str) and v.isdigit():
                out[k] = int(v)
    return out


def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9a-zA-Z_ぁ-んァ-ヶ一-龠ー]+", "", s)
    return s[:24].strip("_") or "spk"
