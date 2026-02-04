from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .project import load_project


@dataclass(frozen=True)
class VisualAssignment:
    seg_id: str
    kind: str  # "image" | "slide"
    source_path: str | None  # project-relative path for kind="image"
    out_path: str  # project-relative path in assets/images


def assign_visuals(project_dir: Path, *, force: bool = False) -> list[VisualAssignment]:
    """
    Creates `assets/images/{seg_id}.(png|jpg)` for each segment:
    - If an article image is available, copy it as the segment image (no slide overlay).
    - Otherwise, generate a simple slide PNG from title + excerpt.

    Writes `assets/images/assignments.json` for traceability.
    """
    _require_pillow()
    project = load_project(project_dir)

    segments = _load_segments_index(project)
    article_images = _load_article_images(project)

    # Map HTML figure placement -> local image paths.
    figures = _extract_figures_with_context(project)
    figure_paths = [f.image_path for f in figures if f.image_path is not None]

    eyecatch_override = project.path("assets", "images", "article", "eyecatch_override.png")
    if eyecatch_override.exists():
        eyecatch = eyecatch_override
    else:
        eyecatch = _pick_eyecatch(figure_paths) or _pick_eyecatch(article_images)

    mapping = _map_figures_to_segments(figures, segments)

    # Prefer eyecatch for first segments if present.
    if eyecatch is not None and segments:
        first = str(segments[0].get("id"))
        mapping.setdefault(first, eyecatch)
        if len(segments) >= 2:
            second = str(segments[1].get("id"))
            # If not already mapped via figure captions, reuse eyecatch for the second segment too.
            mapping.setdefault(second, eyecatch)

    # Fallback: assign remaining screenshots sequentially to segments without an image.
    screenshots = _pick_screenshots(figure_paths) or _pick_screenshots(article_images)
    used_images = set(mapping.values())
    screenshots = [p for p in screenshots if p not in used_images]
    remaining_seg_ids = [s["id"] for s in segments if s["id"] not in mapping and s["id"] != "0015_outro"]
    for seg_id, img_path in zip(remaining_seg_ids, screenshots, strict=False):
        mapping.setdefault(seg_id, img_path)

    out_dir = project.path("assets", "images")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_slide = project.path("assets", "slides", "summary_001.png")

    assignments: list[VisualAssignment] = []
    for seg in segments:
        seg_id = seg["id"]
        title = seg.get("title") or seg_id
        txt_path = project.path(seg["text_path"])
        text = txt_path.read_text(encoding="utf-8").strip()

        if seg_id == "0015_outro" and summary_slide.exists():
            # Preserve the curated summary slide if present.
            out_path = out_dir / "0015_outro.png"
            if force or not out_path.exists():
                shutil.copyfile(summary_slide, out_path)
            assignments.append(
                VisualAssignment(seg_id=seg_id, kind="slide", source_path=summary_slide.relative_to(project.root).as_posix(), out_path=out_path.relative_to(project.root).as_posix())
            )
            continue

        # If we have an assigned image, copy it and delete any previous slide png for that seg_id.
        assigned = mapping.get(seg_id)
        if assigned is not None and assigned.exists():
            out_path = _copy_as_segment_image(out_dir, seg_id, assigned, force=force)
            assignments.append(
                VisualAssignment(
                    seg_id=seg_id,
                    kind="image",
                    source_path=assigned.relative_to(project.root).as_posix(),
                    out_path=out_path.relative_to(project.root).as_posix(),
                )
            )
            continue

        # Otherwise, generate slide image (unless already exists and not force).
        out_path = out_dir / f"{seg_id}.png"
        if out_path.exists() and not force:
            assignments.append(
                VisualAssignment(seg_id=seg_id, kind="slide", source_path=None, out_path=out_path.relative_to(project.root).as_posix())
            )
            continue

        _render_slide_png(out_path, title=title, text=text)
        assignments.append(
            VisualAssignment(seg_id=seg_id, kind="slide", source_path=None, out_path=out_path.relative_to(project.root).as_posix())
        )

    (out_dir / "assignments.json").write_text(
        json.dumps(
            {
                "items": [
                    {"id": a.seg_id, "kind": a.kind, "source_path": a.source_path, "out_path": a.out_path}
                    for a in assignments
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return assignments


@dataclass(frozen=True)
class _Figure:
    image_path: Path | None
    caption: str
    section: str


def _extract_figures_with_context(project) -> list[_Figure]:
    """
    Extracts <figure><img ...><figcaption>...</figcaption></figure> from `source/article.html`,
    tracking the nearest preceding section heading (h2/h3).
    """
    html_path = project.path("source", "article.html")
    if not html_path.exists():
        return []

    url_to_local = _load_downloaded_url_map(project)
    base_url = _extract_source_url_from_article_md(project)

    class P(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.section_h2 = ""
            self.section_h3 = ""
            self.in_fig = False
            self.in_caption = False
            self.cur_img: str | None = None
            self.cur_caption: list[str] = []
            self.figures: list[tuple[str | None, str, str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            t = tag.lower()
            a = {k.lower(): (v or "") for k, v in attrs}
            if t in {"h2", "h3"}:
                # reset text capture
                self._heading_tag = t
                self._heading_buf = []
            if t == "figure":
                self.in_fig = True
                self.cur_img = None
                self.cur_caption = []
            if self.in_fig and t == "img":
                self.cur_img = a.get("src") or a.get("data-src") or self.cur_img
            if self.in_fig and t == "figcaption":
                self.in_caption = True

        def handle_endtag(self, tag: str) -> None:
            t = tag.lower()
            if t in {"h2", "h3"} and getattr(self, "_heading_tag", None) == t:
                text = _clean_text("".join(getattr(self, "_heading_buf", [])))
                if t == "h2":
                    self.section_h2 = text
                    self.section_h3 = ""
                else:
                    self.section_h3 = text
                self._heading_tag = None
                self._heading_buf = []

            if t == "figcaption":
                self.in_caption = False
            if t == "figure" and self.in_fig:
                cap = _clean_text("".join(self.cur_caption))
                section = self.section_h3 or self.section_h2
                self.figures.append((self.cur_img, cap, section))
                self.in_fig = False

        def handle_data(self, data: str) -> None:
            if getattr(self, "_heading_tag", None) in {"h2", "h3"}:
                self._heading_buf.append(data)
            if self.in_caption:
                self.cur_caption.append(data)

    parser = P()
    parser.feed(html_path.read_text(encoding="utf-8", errors="replace"))
    parser.close()

    out: list[_Figure] = []
    for raw_url, cap, section in parser.figures:
        image_path: Path | None = None
        if raw_url:
            try:
                p = urlparse(raw_url).path
            except Exception:
                p = ""
            local_rel = url_to_local.get(p)
            if local_rel:
                image_path = project.path(local_rel)
            elif base_url and raw_url.startswith(("http://", "https://")):
                # Not in the download index; ignore for now.
                image_path = None
        out.append(_Figure(image_path=image_path if image_path and image_path.exists() else None, caption=cap, section=section))
    return out


def _load_downloaded_url_map(project) -> dict[str, str]:
    """
    Map URL path -> local project-relative path from assets/images/article/images.json.
    """
    idx = project.path("assets", "images", "article", "images.json")
    if not idx.exists():
        return {}
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for it in (data.get("items") or []):
        url = it.get("url")
        path = it.get("path")
        if not isinstance(url, str) or not isinstance(path, str):
            continue
        try:
            out[urlparse(url).path] = path
        except Exception:
            continue
    return out


def _extract_source_url_from_article_md(project) -> str | None:
    md = project.path("source", "article.md")
    if not md.exists():
        return None
    lines = md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:60]:
        if line.strip() == "---":
            break
        if line.startswith("source_url:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _map_figures_to_segments(figures: list[_Figure], segments: list[dict]) -> dict[str, Path]:
    """
    Choose figure images per segment by matching figure caption/section to segment titles.
    """
    seg_title: dict[str, str] = {str(s.get("id")): str(s.get("title") or s.get("id")) for s in segments}

    # Normalize helper.
    def norm(s: str) -> str:
        s = unescape(s or "")
        s = s.lower()
        for ch in (" ", "　", "\n", "\t", "・", "—", "–", "-", "＿", "_", "（", "）", "(", ")", ":", "：", "。", ".", "、", ",", "!", "！", "?", "？", "…"):
            s = s.replace(ch, "")
        return s

    def score(fig: _Figure, seg_id: str) -> int:
        title = seg_title.get(seg_id) or ""
        cap = fig.caption or ""
        sec = fig.section or ""
        t = norm(title)
        c = norm(cap)
        s = norm(sec)

        sc = 0
        if c and t:
            if c in t or t in c:
                sc = max(sc, 80 + min(len(c), len(t)))
            # token overlap (rough)
            for token in (cap, sec):
                tn = norm(token)
                if tn and tn in t:
                    sc = max(sc, 60 + len(tn))
        if s and t and (s in t or t in s):
            sc = max(sc, 50 + min(len(s), len(t)))

        # Friendly heuristics for common headings.
        if ("使い方" in title) and ("2-2" in cap or "zip" in cap.lower()):
            sc = max(sc, 90)
        if ("使い方" in title) and ("見える化" in cap):
            sc = max(sc, 85)
        return sc

    mapping: dict[str, Path] = {}
    used_images: set[Path] = set()

    # Prefer captioned figures; keep order.
    figs = [f for f in figures if f.image_path is not None]
    figs.sort(key=lambda f: (0 if f.caption else 1))

    seg_ids = list(seg_title.keys())
    for fig in figs:
        if fig.image_path is None or fig.image_path in used_images:
            continue
        best_id = None
        best = 0
        for sid in seg_ids:
            if sid in mapping:
                continue
            sc = score(fig, sid)
            if sc > best:
                best = sc
                best_id = sid
        if best_id is not None and best >= 60:
            mapping[best_id] = fig.image_path
            used_images.add(fig.image_path)

    return mapping


def _load_segments_index(project) -> list[dict]:
    p = project.path("script", "segments.json")
    if not p.exists():
        raise FileNotFoundError(f"segments.json not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("segments.json must be a list")
    return data


def _load_article_images(project) -> list[Path]:
    # Prefer the downloader index for stable ordering.
    idx = project.path("assets", "images", "article", "images.json")
    if idx.exists():
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
            items = data.get("items") or []
            out: list[Path] = []
            for it in items:
                path = it.get("path")
                if not isinstance(path, str):
                    continue
                p = project.path(path)
                if p.exists():
                    out.append(p)
            return out
        except Exception:
            pass

    # Fallback: just list files in the folder.
    d = project.path("assets", "images", "article")
    if not d.exists():
        return []
    return sorted([p for p in d.iterdir() if p.is_file()])


def _pick_eyecatch(images: list[Path]) -> Path | None:
    for p in images:
        name = p.name.lower()
        if "rectangle_large" in name or "eyecatch" in name:
            return p
    # Otherwise first non-profile image.
    for p in images:
        if "profile_" not in p.name.lower():
            return p
    return None


def _pick_screenshots(images: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in images:
        name = p.name.lower()
        if "profile_" in name:
            continue
        if "rectangle_large" in name or "eyecatch" in name:
            continue
        out.append(p)
    return out


def _copy_as_segment_image(out_dir: Path, seg_id: str, src: Path, *, force: bool) -> Path:
    # Remove any prior png slide if we're switching to an image.
    slide_png = out_dir / f"{seg_id}.png"
    if slide_png.exists() and slide_png.resolve() != src.resolve():
        slide_png.unlink()

    ext = src.suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg"}:
        # Convert to png.
        out_path = out_dir / f"{seg_id}.png"
        if out_path.exists() and not force:
            return out_path
        from PIL import Image

        im = Image.open(src).convert("RGB")
        im.save(out_path)
        return out_path

    out_path = out_dir / f"{seg_id}{ext}"
    if out_path.exists() and not force:
        return out_path
    shutil.copyfile(src, out_path)
    return out_path


def _render_slide_png(out_path: Path, *, title: str, text: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    # Light green theme, text-only slide.
    W, H = 1920, 1080
    bg = (224, 244, 232)  # pale mint
    fg = (16, 34, 24)
    muted = (70, 94, 82)
    accent = (38, 140, 90)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    title_font = ImageFont.truetype(font_path, 84)
    body_font = ImageFont.truetype(font_path, 52)

    margin_x = 140
    margin_top = 120

    d.text((margin_x, margin_top), title, font=title_font, fill=fg)
    bar_y = margin_top + 110
    d.rounded_rectangle((margin_x, bar_y, margin_x + 320, bar_y + 10), radius=6, fill=accent)

    excerpt = " ".join(text.strip().split())
    if len(excerpt) > 220:
        excerpt = excerpt[:220].rstrip("。") + "。"

    y = bar_y + 60
    lines = _wrap_text(d, excerpt, body_font, max_width=W - margin_x * 2)[:7]
    if not lines:
        lines = ["（本文なし）"]
    for line in lines:
        d.text((margin_x, y), line, font=body_font, fill=muted)
        y += 64

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, max_width: int) -> list[str]:
    # Width-based wrapping that works even for Japanese (no spaces).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    if not parts:
        return []

    out: list[str] = []
    for part in parts:
        out.extend(_wrap_one(draw, part, font, max_width=max_width))
    return out


def _wrap_one(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, max_width: int) -> list[str]:
    # Prefer splitting by Japanese sentence delimiter if it helps.
    sentences = [s for s in text.split("。") if s]
    if len(sentences) >= 2:
        lines: list[str] = []
        for s in sentences:
            chunk = s + "。"
            lines.extend(_wrap_chars(draw, chunk, font, max_width=max_width))
        return lines
    return _wrap_chars(draw, text, font, max_width=max_width)


def _wrap_chars(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, max_width: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    lines: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] <= max_width or not cur:
            cur = trial
            continue
        lines.append(cur)
        cur = ch
    if cur:
        lines.append(cur)
    return lines


def _clean_text(s: str) -> str:
    s = unescape(s or "")
    return " ".join(s.split()).strip()


def _require_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "この機能（visuals/スライド生成）には Pillow が必要です。\n"
            "インストール: python -m pip install -r requirements.txt"
        ) from e
