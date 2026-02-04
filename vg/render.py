from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .project import load_project


@dataclass(frozen=True)
class RenderSettings:
    width: int
    height: int
    fps: int


def render_long(project_dir: Path, out: str | None, fontfile: str | None, force: bool) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg が見つかりません。macOS なら `brew install ffmpeg` の後に再実行してください。"
        )

    project = load_project(project_dir)
    settings = _load_long_settings(project)
    has_drawtext = _ffmpeg_has_filter("drawtext")
    if not has_drawtext:
        print("WARN: ffmpeg に drawtext フィルタが無いため、プレースホルダーにはタイトル文字を描画しません。")

    article_images_by_title = _collect_article_images_by_title(project)
    fallback_image = _find_fallback_image(project)

    timeline_path = project.path("script", "timeline.json")
    if not timeline_path.exists():
        raise FileNotFoundError(f"timeline.json not found: {timeline_path} (run: python -m vg timeline {project.root})")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    items = timeline.get("items") or []

    segments_dir = project.path("render", "segments_long")
    segments_dir.mkdir(parents=True, exist_ok=True)

    seg_mp4s: list[Path] = []
    for idx, item in enumerate(items, start=1):
        seg_id = item["id"]
        title = item.get("title") or seg_id
        wav_path = project.path(item["wav_path"])
        if not wav_path.exists():
            raise FileNotFoundError(f"wav not found: {wav_path}")

        duration = float(item["end"]) - float(item["start"])
        mp4_path = segments_dir / f"{idx:04d}_{seg_id}.mp4"
        seg_mp4s.append(mp4_path)

        if mp4_path.exists() and not force:
            continue

        img = _find_segment_image(project, seg_id)
        if img is None:
            img = _pick_article_image(article_images_by_title, title)
        if img is None and fallback_image is not None:
            img = fallback_image
        if img is None:
            _render_placeholder_segment(
                out_path=mp4_path,
                wav_path=wav_path,
                duration=duration,
                title=title,
                settings=settings,
                fontfile=fontfile,
                drawtext_enabled=has_drawtext,
            )
        else:
            _render_image_segment(
                out_path=mp4_path,
                image_path=img,
                wav_path=wav_path,
                duration=duration,
                settings=settings,
            )

    concat_list = project.path("render", "concat_long.txt")
    concat_list.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in seg_mp4s:
        rel = p.relative_to(concat_list.parent)
        lines.append(f"file '{rel.as_posix()}'")
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_path = project.path(out) if out else project.path("export", "master_long.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # まずは stream copy を試し、ダメなら再エンコードで確実に通す
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(out_path),
        ],
        retry_with_reencode=True,
        reencode_args=[
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(settings.fps),
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ],
    )


def _load_long_settings(project) -> RenderSettings:
    video = project.config.get("video", {})
    long_cfg = video.get("long", {}) if isinstance(video, dict) else {}
    width = int(long_cfg.get("width", 1920))
    height = int(long_cfg.get("height", 1080))
    fps = int(long_cfg.get("fps", 30))
    return RenderSettings(width=width, height=height, fps=fps)


def _find_segment_image(project, seg_id: str) -> Path | None:
    base = project.path("assets", "images")
    for ext in ("png", "jpg", "jpeg"):
        p = base / f"{seg_id}.{ext}"
        if p.exists():
            return p
    return None


def _find_fallback_image(project) -> Path | None:
    # 章画像が見つからない場合の共通フォールバック
    candidates = [
        project.path("assets", "images", "fallback.png"),
        project.path("assets", "images", "fallback.jpg"),
        project.path("assets", "images", "fallback.jpeg"),
        project.path("assets", "images", "article", "fallback.png"),
        project.path("assets", "images", "article", "fallback.jpg"),
        project.path("assets", "images", "article", "fallback.jpeg"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


_md_heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_md_image_re = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_html_img_re = re.compile(r"""<img[^>]+src=["']([^"']+)["'][^>]*>""", re.IGNORECASE)


def _collect_article_images_by_title(project) -> dict[str, list[Path]]:
    md_path = project.path("source", "article.md")
    if not md_path.exists():
        return {}

    text = md_path.read_text(encoding="utf-8")
    current_title: str | None = None
    out: dict[str, list[Path]] = {}

    for line in text.splitlines():
        m = _md_heading_re.match(line)
        if m:
            current_title = m.group(2).strip()
            out.setdefault(current_title, [])
            continue
        if current_title is None:
            continue

        for img in _extract_images_from_line(md_path, line):
            out[current_title].append(img)

    # 重複排除（順序は保持）
    for k, imgs in out.items():
        seen: set[Path] = set()
        deduped: list[Path] = []
        for p in imgs:
            if p in seen:
                continue
            seen.add(p)
            deduped.append(p)
        out[k] = deduped

    return out


def _extract_images_from_line(md_path: Path, line: str) -> list[Path]:
    urls: list[str] = []
    for m in _md_image_re.finditer(line):
        urls.append(m.group(1).strip())
    for m in _html_img_re.finditer(line):
        urls.append(m.group(1).strip())

    paths: list[Path] = []
    for url in urls:
        # "path title" 形式の title は削る（雑に最初の空白で分割）
        url = url.strip().strip("<>")
        if " " in url:
            url = url.split(" ", 1)[0].strip()
        if url.startswith(("http://", "https://")):
            continue
        candidate = (md_path.parent / url).resolve()
        if candidate.exists():
            paths.append(candidate)
    return paths


def _pick_article_image(images_by_title: dict[str, list[Path]], title: str) -> Path | None:
    imgs = images_by_title.get(title)
    if imgs:
        return imgs[0]
    return None


def _render_image_segment(
    *,
    out_path: Path,
    image_path: Path,
    wav_path: Path,
    duration: float,
    settings: RenderSettings,
) -> None:
    vf = (
        f"scale={settings.width}:{settings.height}:force_original_aspect_ratio=decrease,"
        f"pad={settings.width}:{settings.height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "format=yuv420p"
    )
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(image_path),
            "-i",
            str(wav_path),
            "-vf",
            vf,
            "-r",
            str(settings.fps),
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
    )


def _render_placeholder_segment(
    *,
    out_path: Path,
    wav_path: Path,
    duration: float,
    title: str,
    settings: RenderSettings,
    fontfile: str | None,
    drawtext_enabled: bool,
) -> None:
    vf: str | None = None
    if drawtext_enabled:
        title_file = out_path.with_suffix(".txt")
        title_file.write_text(title + "\n", encoding="utf-8")

        draw = (
            f"drawtext=textfile='{title_file.as_posix()}':reload=0:"
            "fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2"
        )
        if fontfile:
            draw = (
                f"drawtext=fontfile='{Path(fontfile).as_posix()}':"
                f"textfile='{title_file.as_posix()}':reload=0:"
                "fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2"
            )
        vf = draw

    args = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-t",
        f"{duration:.3f}",
        "-i",
        f"color=c=black:s={settings.width}x{settings.height}:r={settings.fps}",
        "-i",
        str(wav_path),
    ]
    if vf:
        args += ["-vf", vf]
    args += [
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


def _run_ffmpeg(args: list[str], retry_with_reencode: bool = False, reencode_args: list[str] | None = None) -> None:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode == 0:
        return
    if retry_with_reencode and reencode_args:
        proc2 = subprocess.run(reencode_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc2.returncode == 0:
            return
        tail = "\n".join((proc2.stderr or "").splitlines()[-40:])
        raise RuntimeError(f"ffmpeg failed (reencode). args={reencode_args}\n{tail}")

    tail = "\n".join((proc.stderr or "").splitlines()[-40:])
    raise RuntimeError(f"ffmpeg failed. args={args}\n{tail}")


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
