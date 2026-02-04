from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .project import load_project


@dataclass(frozen=True)
class ShortsLayout:
    caption_height_ratio: float
    caption_box_alpha: float


def render_shorts(
    project_dir: Path,
    *,
    in_path: str | None,
    out_dir: str | None,
    one_id: str | None,
    title: str | None,
    start: float | None,
    end: float | None,
    segments: str | None,
    fontfile: str | None,
    force: bool,
) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg が見つかりません。macOS なら `brew install ffmpeg` の後に再実行してください。"
        )

    project = load_project(project_dir)
    has_drawtext = _ffmpeg_has_filter("drawtext")
    if not has_drawtext:
        print("WARN: ffmpeg に drawtext フィルタが無いため、Shorts のタイトル文字は描画しません。")

    src = project.path(in_path) if in_path else project.path("export", "master_long.mp4")
    if not src.exists():
        raise FileNotFoundError(f"input mp4 not found: {src} (run: python -m vg render {project.root})")

    layout = _load_layout(project)
    video_cfg = project.config.get("video", {})
    shorts_cfg = video_cfg.get("shorts", {}) if isinstance(video_cfg, dict) else {}
    out_w = int(shorts_cfg.get("width", 1080))
    out_h = int(shorts_cfg.get("height", 1920))
    fps = int(shorts_cfg.get("fps", 30))

    resolved_out_dir = project.path(out_dir) if out_dir else project.path("export", "shorts")
    resolved_out_dir.mkdir(parents=True, exist_ok=True)

    # 1本だけ作るモード
    if start is not None or end is not None or segments is not None:
        spec = _one_off_spec(
            project,
            one_id=one_id,
            title=title,
            start=start,
            end=end,
            segments=segments,
        )
        out_path = resolved_out_dir / f"{_safe_stem(spec.id)}.mp4"
        _render_one_short(
            src=src,
            out_path=out_path,
            start=spec.start,
            end=spec.end,
            title=spec.title,
            out_w=out_w,
            out_h=out_h,
            fps=fps,
            layout=layout,
            fontfile=fontfile,
            drawtext_enabled=has_drawtext,
            force=force,
        )
        return

    # project.json の shorts 配列から作る
    shorts_list = project.config.get("shorts") or []
    if not shorts_list:
        raise RuntimeError(
            "shorts 設定がありません。project.json の shorts に追加するか、"
            "`--start/--end` または `--segments` で 1 本だけ指定してください。"
        )

    for idx, entry in enumerate(shorts_list, start=1):
        spec = _spec_from_entry(project, entry, default_id=f"{idx:02d}")
        out_path = resolved_out_dir / f"{idx:02d}_{_safe_stem(spec.id)}.mp4"
        _render_one_short(
            src=src,
            out_path=out_path,
            start=spec.start,
            end=spec.end,
            title=spec.title,
            out_w=out_w,
            out_h=out_h,
            fps=fps,
            layout=layout,
            fontfile=fontfile,
            drawtext_enabled=has_drawtext,
            force=force,
        )


@dataclass(frozen=True)
class ShortSpec:
    id: str
    title: str | None
    start: float
    end: float


def _one_off_spec(
    project,
    *,
    one_id: str | None,
    title: str | None,
    start: float | None,
    end: float | None,
    segments: str | None,
) -> ShortSpec:
    resolved_id = one_id or "one_off"
    if segments:
        segs = [s.strip() for s in segments.split(",") if s.strip()]
        if not segs:
            raise ValueError("segments is empty")
        s, e = _range_from_segments(project, segs)
        return ShortSpec(id=resolved_id, title=title, start=s, end=e)
    if start is None or end is None:
        raise ValueError("start/end are required unless segments is provided")
    if end <= start:
        raise ValueError("end must be greater than start")
    return ShortSpec(id=resolved_id, title=title, start=float(start), end=float(end))


def _spec_from_entry(project, entry: dict, default_id: str) -> ShortSpec:
    if not isinstance(entry, dict):
        raise ValueError("shorts entry must be an object")
    sid = str(entry.get("id") or default_id)
    title = entry.get("title")

    if "segments" in entry and entry["segments"] is not None:
        segs = entry["segments"]
        if not isinstance(segs, list) or not segs:
            raise ValueError(f"shorts[{sid}].segments must be a non-empty array")
        seg_ids = [str(s) for s in segs]
        s, e = _range_from_segments(project, seg_ids)
        return ShortSpec(id=sid, title=str(title) if title is not None else None, start=s, end=e)

    if "start" in entry and "end" in entry:
        s = float(entry["start"])
        e = float(entry["end"])
        if e <= s:
            raise ValueError(f"shorts[{sid}] end must be greater than start")
        return ShortSpec(id=sid, title=str(title) if title is not None else None, start=s, end=e)

    raise ValueError(f"shorts[{sid}] requires either (segments) or (start,end)")


def _range_from_segments(project, seg_ids: list[str]) -> tuple[float, float]:
    timeline_path = project.path("script", "timeline.json")
    if not timeline_path.exists():
        raise FileNotFoundError(
            f"timeline.json not found: {timeline_path} (run: python -m vg timeline {project.root})"
        )
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    items = timeline.get("items") or []
    by_id = {it["id"]: it for it in items}

    missing = [sid for sid in seg_ids if sid not in by_id]
    if missing:
        raise KeyError(f"segment id not found in timeline: {missing}")

    start = min(float(by_id[sid]["start"]) for sid in seg_ids)
    end = max(float(by_id[sid]["end"]) for sid in seg_ids)
    return start, end


def _load_layout(project) -> ShortsLayout:
    cfg = project.config.get("shorts_layout", {}) if isinstance(project.config, dict) else {}
    return ShortsLayout(
        caption_height_ratio=float(cfg.get("caption_height_ratio", 0.28)),
        caption_box_alpha=float(cfg.get("caption_box_alpha", 0.35)),
    )


def _render_one_short(
    *,
    src: Path,
    out_path: Path,
    start: float,
    end: float,
    title: str | None,
    out_w: int,
    out_h: int,
    fps: int,
    layout: ShortsLayout,
    fontfile: str | None,
    drawtext_enabled: bool,
    force: bool,
) -> None:
    if out_path.exists() and not force:
        return

    duration = end - start
    if duration <= 0:
        raise ValueError("invalid duration")

    cap_h = int(out_h * max(0.0, min(0.6, layout.caption_height_ratio)))
    fg_h = out_h - cap_h

    # 背景: cover + blur
    bg = (
        f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},gblur=sigma=30[bg]"
    )
    # 前景: contain + pad（縦に撮り直した素材はそのままフィットしやすい）
    fg = (
        f"[0:v]scale={out_w}:{fg_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{fg_h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg]"
    )
    overlay = f"[bg][fg]overlay=0:0[v0]"
    box = f"[v0]drawbox=x=0:y={fg_h}:w={out_w}:h={cap_h}:color=black@{layout.caption_box_alpha}:t=fill[v1]"

    vf_chain = ";".join([bg, fg, overlay, box])
    if title and drawtext_enabled:
        title_file = out_path.with_suffix(".title.txt")
        title_file.write_text(title + "\n", encoding="utf-8")
        draw = (
            f"[v1]drawtext=textfile='{title_file.as_posix()}':reload=0:"
            "fontcolor=white:fontsize=48:"
            f"x=48:y={fg_h}+48[v2]"
        )
        if fontfile:
            draw = (
                f"[v1]drawtext=fontfile='{Path(fontfile).as_posix()}':"
                f"textfile='{title_file.as_posix()}':reload=0:"
                "fontcolor=white:fontsize=48:"
                f"x=48:y={fg_h}+48[v2]"
            )
        vf_chain = vf_chain + ";" + draw
        v_out = "[v2]"
    else:
        v_out = "[v1]"

    args = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(src),
        "-filter_complex",
        vf_chain,
        "-map",
        v_out,
        "-map",
        "0:a?",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(out_path),
    ]
    _run_ffmpeg(args)


def _run_ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode == 0:
        return
    tail = "\n".join((proc.stderr or "").splitlines()[-40:])
    raise RuntimeError(f"ffmpeg failed. args={args}\n{tail}")


_safe_stem_re = re.compile(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー_\\-]+")


def _safe_stem(s: str) -> str:
    s = s.strip()
    s = s.replace(" ", "_")
    s = _safe_stem_re.sub("", s)
    return s[:80] or "short"


def _ffmpeg_has_filter(name: str) -> bool:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False

    hay = proc.stdout or ""
    return bool(re.search(rf"(^|\s){re.escape(name)}(\s|$)", hay, flags=re.MULTILINE))
