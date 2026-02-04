from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    id: str
    title: str
    text: str


_md_heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

_yaml_fm_delim_re = re.compile(r"^---\s*$")


def _strip_yaml_frontmatter(markdown: str) -> str:
    # Common pattern: YAML frontmatter at very top.
    lines = markdown.splitlines()
    if not lines or not _yaml_fm_delim_re.match(lines[0]):
        return markdown
    for i in range(1, len(lines)):
        if _yaml_fm_delim_re.match(lines[i]):
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return markdown


def _strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    return text


def split_markdown_into_segments(markdown: str) -> list[Segment]:
    markdown = _strip_yaml_frontmatter(markdown)
    lines = markdown.splitlines()
    current_title = "intro"
    buf: list[str] = []
    segments: list[Segment] = []

    def flush() -> None:
        nonlocal buf, current_title
        body = "\n".join(buf).strip()
        if not body:
            buf = []
            return
        segments.append(
            Segment(
                id="",
                title=current_title,
                text=_strip_markdown(body).strip(),
            )
        )
        buf = []

    for line in lines:
        m = _md_heading_re.match(line)
        if m:
            flush()
            current_title = m.group(2).strip()
            continue
        buf.append(line)
    flush()

    out: list[Segment] = []
    for idx, seg in enumerate(segments, start=1):
        seg_id = f"{idx:04d}_{_slugify(seg.title) or 'section'}"
        out.append(Segment(id=seg_id, title=seg.title, text=_normalize_text(seg.text)))
    return out


def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9a-zA-Z_ぁ-んァ-ヶ一-龠ー]+", "", s)
    return s[:40].strip("_")


def _normalize_text(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def build_script_segments(project_dir: Path, source_relpath: str = "source/article.md") -> None:
    project_dir = project_dir.resolve()
    source_path = project_dir / source_relpath
    if not source_path.exists():
        raise FileNotFoundError(f"source not found: {source_path}")

    md = source_path.read_text(encoding="utf-8")
    segments = split_markdown_into_segments(md)

    seg_dir = project_dir / "script" / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for seg in segments:
        txt_path = seg_dir / f"{seg.id}.txt"
        txt_path.write_text(seg.text + "\n", encoding="utf-8")
        index.append({"id": seg.id, "title": seg.title, "text_path": f"script/segments/{seg.id}.txt"})

    (project_dir / "script").mkdir(parents=True, exist_ok=True)
    (project_dir / "script" / "segments.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
