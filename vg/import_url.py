from __future__ import annotations

import gzip
import json
import re
import time
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .images import fetch_images
from .init_project import init_project


@dataclass
class ImportedArticle:
    project_dir: Path
    url: str
    final_url: str
    title: str
    md_relpath: str
    html_relpath: str


def import_url(
    url: str,
    *,
    slug: str | None = None,
    force: bool = False,
    fetch_article_images: bool = False,
    rewrite_images: bool = False,
) -> ImportedArticle:
    html, final_url, title = _fetch_html(url)
    slug = slug or _suggest_slug(final_url, title)

    project_dir = init_project(slug).resolve()
    md_path = project_dir / "source" / "article.md"
    html_path = project_dir / "source" / "article.html"

    if md_path.exists() and not force:
        raise FileExistsError(f"already exists: {md_path} (use --force to overwrite)")

    html_path.write_text(html, encoding="utf-8")

    md = _html_to_markdown(html, base_url=final_url, title=title)
    md_path.write_text(md, encoding="utf-8")

    _maybe_update_project_title(project_dir, title=title, slug=slug)

    if fetch_article_images:
        fetch_images(
            project_dir,
            md_relpath="source/article.md",
            out_relpath="assets/images/article",
            rewrite=rewrite_images,
        )

    return ImportedArticle(
        project_dir=project_dir,
        url=url,
        final_url=final_url,
        title=title,
        md_relpath="source/article.md",
        html_relpath="source/article.html",
    )


def _fetch_html(url: str) -> tuple[str, str, str]:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip",
        },
        method="GET",
    )
    with urlopen(req) as resp:
        final_url = resp.geturl()
        data = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            data = gzip.decompress(data)

        encoding = resp.headers.get_content_charset() or _sniff_charset(data) or "utf-8"
        html = data.decode(encoding, errors="replace")

    title = _extract_title(html) or _fallback_title_from_url(final_url)
    return html, final_url, title


_charset_re = re.compile(br"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", re.IGNORECASE)


def _sniff_charset(data: bytes) -> str | None:
    head = data[:20_000]
    m = _charset_re.search(head)
    if not m:
        return None
    try:
        return m.group(1).decode("ascii", errors="ignore") or None
    except Exception:
        return None


def _extract_title(html: str) -> str | None:
    # Prefer OpenGraph title if present.
    m = re.search(
        r"""<meta\s+[^>]*(?:property|name)=["']og:title["'][^>]*content=["']([^"']+)["'][^>]*>""",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        return _clean_text(m.group(1))

    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return _clean_text(m.group(1))
    return None


def _fallback_title_from_url(url: str) -> str:
    parsed = urlparse(url)
    last = Path(parsed.path).name or parsed.netloc
    return last or "article"


def _suggest_slug(url: str, title: str) -> str:
    parsed = urlparse(url)
    base = Path(parsed.path).stem or parsed.netloc or title or "article"
    base = base.strip().lower()
    base = re.sub(r"[^0-9a-zA-Zぁ-んァ-ヶ一-龠ー_-]+", "_", base).strip("_")
    return base or "article"


def _maybe_update_project_title(project_dir: Path, *, title: str, slug: str) -> None:
    project_json = project_dir / "project.json"
    if not project_json.exists():
        return

    try:
        data = json.loads(project_json.read_text(encoding="utf-8"))
    except Exception:
        return

    if not isinstance(data, dict):
        return
    if data.get("title") not in (None, "", slug):
        return

    data["title"] = title
    project_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _html_to_markdown(html: str, *, base_url: str, title: str) -> str:
    doc = _HtmlDoc.parse(html)
    main = doc.pick_main() or doc.root

    rendered = _MarkdownRenderer(base_url=base_url).render(main).strip()
    rendered = _collapse_blank_lines(rendered)

    front = [
        "---",
        f"source_url: {base_url}",
        f"fetched_at: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    body = rendered
    if body.startswith("# "):
        # Avoid double H1.
        body = "\n".join(body.splitlines()[1:]).lstrip()

    return "\n".join(front) + (body + "\n" if body else "")


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _clean_text(s: str) -> str:
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\s+([。、！？])", r"\1", s)
    return s


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list["_Node | str"] = field(default_factory=list)

    def iter_nodes(self) -> Iterable["_Node"]:
        yield self
        for c in self.children:
            if isinstance(c, _Node):
                yield from c.iter_nodes()

    def text_content(self) -> str:
        if self.tag in {"script", "style", "noscript", "svg"}:
            return ""
        out: list[str] = []
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            else:
                out.append(c.text_content())
        return " ".join(out)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self._stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        node = _Node(tag.lower(), attr_map)
        self._stack[-1].children.append(node)
        if tag.lower() not in {"meta", "link", "img", "br", "hr", "input"}:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == t:
                self._stack = self._stack[:i]
                return

    def handle_data(self, data: str) -> None:
        txt = _clean_text(data)
        if not txt:
            return
        self._stack[-1].children.append(txt)


@dataclass
class _HtmlDoc:
    root: _Node

    @staticmethod
    def parse(html: str) -> "_HtmlDoc":
        parser = _TreeBuilder()
        parser.feed(html)
        parser.close()
        return _HtmlDoc(root=parser.root)

    def pick_main(self) -> _Node | None:
        # Prefer semantic containers if present.
        preferred = ("article", "main")
        for tag in preferred:
            best = self._pick_largest_by_tag(tag)
            if best is not None:
                return best

        # Otherwise pick the largest content-ish container.
        best_node: _Node | None = None
        best_score = 0
        for n in self.root.iter_nodes():
            if n.tag not in {"div", "section"}:
                continue
            if _looks_like_navigation(n):
                continue
            score = len(_clean_text(n.text_content()))
            if score > best_score:
                best_score = score
                best_node = n
        return best_node

    def _pick_largest_by_tag(self, tag: str) -> _Node | None:
        best_node: _Node | None = None
        best_score = 0
        for n in self.root.iter_nodes():
            if n.tag != tag:
                continue
            if _looks_like_navigation(n):
                continue
            score = len(_clean_text(n.text_content()))
            if score > best_score:
                best_score = score
                best_node = n
        return best_node


def _looks_like_navigation(n: _Node) -> bool:
    if n.tag in {"nav", "header", "footer"}:
        return True
    cls = (n.attrs.get("class") or "").lower()
    if any(k in cls for k in ("nav", "header", "footer", "menu", "breadcrumb", "sidebar", "share")):
        return True
    return False


class _MarkdownRenderer:
    def __init__(self, *, base_url: str) -> None:
        self._base_url = base_url

    def render(self, node: _Node) -> str:
        lines: list[str] = []
        self._render_block(node, lines, list_stack=[])
        return "\n".join(lines).strip()

    def _render_block(self, node: _Node, lines: list[str], *, list_stack: list[dict[str, Any]]) -> None:
        tag = node.tag
        if tag in {"script", "style", "noscript", "svg", "header", "footer", "nav"}:
            return

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            text = self._render_inline_children(node).strip()
            if text:
                lines.append(f"{'#' * level} {text}")
                lines.append("")
            return

        if tag == "p":
            text = self._render_inline_children(node).strip()
            if text:
                lines.append(text)
                lines.append("")
            return

        if tag == "blockquote":
            buf: list[str] = []
            for c in node.children:
                if isinstance(c, _Node):
                    tmp: list[str] = []
                    self._render_block(c, tmp, list_stack=list_stack.copy())
                    buf.extend(tmp)
                else:
                    buf.append(_clean_text(c))
            quote = "\n".join([b for b in buf if b.strip()]).strip()
            if quote:
                for qline in quote.splitlines():
                    lines.append("> " + qline)
                lines.append("")
            return

        if tag in {"ul", "ol"}:
            list_stack.append({"type": tag, "i": 0})
            for c in node.children:
                if isinstance(c, _Node):
                    self._render_block(c, lines, list_stack=list_stack)
            list_stack.pop()
            lines.append("")
            return

        if tag == "li":
            if not list_stack:
                prefix = "- "
            else:
                top = list_stack[-1]
                if top["type"] == "ol":
                    top["i"] += 1
                    prefix = f"{top['i']}. "
                else:
                    prefix = "- "

            text = self._render_inline_children(node).strip()
            if text:
                lines.append(prefix + text)
            else:
                lines.append(prefix.strip())
            return

        if tag == "pre":
            code = _clean_text(node.text_content())
            if code:
                lines.append("```")
                lines.extend(code.splitlines())
                lines.append("```")
                lines.append("")
            return

        if tag == "br":
            lines.append("")
            return

        # Default: render children.
        for c in node.children:
            if isinstance(c, _Node):
                self._render_block(c, lines, list_stack=list_stack)
            else:
                txt = _clean_text(c)
                if txt:
                    lines.append(txt)
                    lines.append("")

    def _render_inline_children(self, node: _Node) -> str:
        parts: list[str] = []
        for c in node.children:
            if isinstance(c, str):
                parts.append(_clean_text(c))
            else:
                parts.append(self._render_inline(c))
        return _clean_text(" ".join([p for p in parts if p.strip()]))

    def _render_inline(self, node: _Node) -> str:
        tag = node.tag
        if tag in {"script", "style", "noscript", "svg"}:
            return ""

        if tag == "a":
            href = (node.attrs.get("href") or "").strip()
            text = self._render_inline_children(node).strip() or href
            if not href:
                return text
            abs_url = urljoin(self._base_url, href)
            return f"[{text}]({abs_url})"

        if tag == "img":
            src = (node.attrs.get("src") or "").strip()
            alt = (node.attrs.get("alt") or "").strip()
            if not src:
                return ""
            abs_url = urljoin(self._base_url, src)
            return f"![{alt}]({abs_url})" if alt else f"![]({abs_url})"

        if tag in {"strong", "b"}:
            inner = self._render_inline_children(node).strip()
            return f"**{inner}**" if inner else ""

        if tag in {"em", "i"}:
            inner = self._render_inline_children(node).strip()
            return f"*{inner}*" if inner else ""

        if tag == "code":
            inner = self._render_inline_children(node).strip()
            inner = inner.replace("`", r"\`")
            return f"`{inner}`" if inner else ""

        if tag == "br":
            return "\n"

        # Inline fallback.
        return self._render_inline_children(node)
