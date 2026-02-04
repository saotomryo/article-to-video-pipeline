from __future__ import annotations

import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


_md_image_re = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_html_img_re = re.compile(r"""<img[^>]+(?:src|data-src)=["']([^"']+)["'][^>]*>""", re.IGNORECASE)


@dataclass(frozen=True)
class DownloadedImage:
    original_url: str
    local_relpath: str
    bytes: int


def fetch_images(project_dir: Path, *, md_relpath: str, out_relpath: str, rewrite: bool) -> list[DownloadedImage]:
    project_dir = project_dir.resolve()
    md_path = project_dir / md_relpath
    if not md_path.exists():
        raise FileNotFoundError(f"markdown not found: {md_path}")

    out_dir = project_dir / out_relpath
    out_dir.mkdir(parents=True, exist_ok=True)

    md = md_path.read_text(encoding="utf-8")
    base_url = _extract_source_url_from_markdown(md)
    urls = list(_extract_image_urls_from_markdown(md, base_url=base_url))
    # Fallback: some pages (e.g. note.com) omit <img> in generated Markdown.
    html_path = project_dir / "source" / "article.html"
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8", errors="replace")
        urls.extend(_extract_image_urls_from_html(html, base_url=base_url))
        urls = _dedupe_preserve_order_by(
            urls,
            key=lambda u: (urlparse(u).scheme, urlparse(u).netloc, urlparse(u).path),
        )
    if not urls:
        return []

    downloaded: list[DownloadedImage] = []
    mapping: dict[str, str] = {}

    for url in urls:
        local_path = _suggest_path(out_dir, url)
        data = _download(url)
        local_path.write_bytes(data)
        rel = local_path.relative_to(project_dir).as_posix()
        downloaded.append(DownloadedImage(original_url=url, local_relpath=rel, bytes=len(data)))
        mapping[url] = rel
        time.sleep(0.1)

    (out_dir / "images.json").write_text(
        json.dumps(
            {
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "items": [{"url": d.original_url, "path": d.local_relpath, "bytes": d.bytes} for d in downloaded],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if rewrite:
        md2 = _rewrite_markdown_images(md, project_dir=project_dir, md_path=md_path, url_to_rel=mapping)
        if md2 != md:
            md_path.write_text(md2, encoding="utf-8")

    return downloaded


def _extract_source_url_from_markdown(markdown: str) -> str | None:
    # Read only from top YAML-ish block to avoid false positives.
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:60]:
        if line.strip() == "---":
            break
        if line.startswith("source_url:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _extract_image_urls_from_markdown(markdown: str, *, base_url: str | None) -> Iterable[str]:
    for m in _md_image_re.finditer(markdown):
        url = m.group(1).strip()
        url = _absolutize(url, base_url)
        if url:
            yield url


def _extract_image_urls_from_html(html: str, *, base_url: str | None) -> list[str]:
    parser = _ImageUrlHTMLParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return parser.urls


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    return _dedupe_preserve_order_by(items, key=lambda x: x)


def _dedupe_preserve_order_by(items: list[str], *, key) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = key(x)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _absolutize(url: str, base_url: str | None) -> str | None:
    url = unescape(url.strip().strip('"').strip("'"))
    if not url or url.startswith(("data:", "javascript:", "about:")):
        return None
    if url.startswith(("http://", "https://")):
        return url
    if base_url:
        return urljoin(base_url, url)
    return None


def _parse_srcset(srcset: str) -> list[str]:
    # "url 1x, url2 2x" or "url 400w, url2 800w"
    out: list[str] = []
    for part in srcset.split(","):
        token = part.strip().split()
        if not token:
            continue
        out.append(token[0].strip())
    return out


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg"}


def _looks_like_image_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    suffix = Path(p.path).suffix.lower()
    if suffix in _IMAGE_EXTS:
        return True
    # Some CDNs omit extensions but are clearly image endpoints.
    host = (p.netloc or "").lower()
    if "assets.st-note.com" in host:
        return True
    return False


class _ImageUrlHTMLParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}

        if tag == "img":
            self._add_one(a.get("src"))
            self._add_one(a.get("data-src"))
            self._add_one(a.get("data-original"))
            self._add_one(a.get("data-lazy-src"))

            for u in _parse_srcset(a.get("srcset") or ""):
                self._add_one(u)
            for u in _parse_srcset(a.get("data-srcset") or ""):
                self._add_one(u)

        if tag == "source":
            for u in _parse_srcset(a.get("srcset") or ""):
                self._add_one(u)

        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in {"og:image", "twitter:image", "twitter:image:src"}:
                self._add_one(a.get("content"))

        if tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "image_src":
                self._add_one(a.get("href"))
            if rel == "preload" and (a.get("as") or "").lower() == "image":
                self._add_one(a.get("href"))

    def _add_one(self, url: str | None) -> None:
        if not url:
            return
        abs_url = _absolutize(url, self._base_url)
        if not abs_url:
            return
        if not _looks_like_image_url(abs_url):
            return
        self.urls.append(abs_url)


def _download(url: str) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
        method="GET",
    )
    with urlopen(req) as resp:
        return resp.read()


def _suggest_path(out_dir: Path, url: str) -> Path:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if not name:
        name = "image"

    # クエリは無視して拡張子を保つ
    stem = Path(name).stem
    suffix = Path(name).suffix
    if not suffix:
        guessed, _ = mimetypes.guess_type(parsed.path)
        suffix = mimetypes.guess_extension(guessed or "") or ".img"

    safe_stem = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー_-]+", "_", stem).strip("_") or "image"
    base = out_dir / f"{safe_stem}{suffix}"

    if not base.exists():
        return base

    # 重複時は連番
    for i in range(2, 1000):
        cand = out_dir / f"{safe_stem}_{i}{suffix}"
        if not cand.exists():
            return cand

    raise RuntimeError(f"too many duplicate filenames for url: {url}")


def _rewrite_markdown_images(markdown: str, *, project_dir: Path, md_path: Path, url_to_rel: dict[str, str]) -> str:
    # mdファイルから見た相対パスに変換して置換
    md_dir = md_path.parent

    def to_local(url: str) -> str:
        rel = url_to_rel.get(url)
        if not rel:
            return url
        abs_path = (project_dir / rel).resolve()
        return os.path.relpath(abs_path, start=md_dir.resolve()).replace(os.sep, "/")

    def repl_md(m: re.Match) -> str:
        url = m.group(1).strip()
        return m.group(0).replace(url, to_local(url))

    def repl_html(m: re.Match) -> str:
        url = m.group(1).strip()
        return m.group(0).replace(url, to_local(url))

    out = _md_image_re.sub(repl_md, markdown)
    out = _html_img_re.sub(repl_html, out)
    return out
