"""MkDocs hooks for metadata-driven learning-series navigation."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.site import collect_documents  # noqa: E402


SERIES: DefaultDict[str, List[Tuple[int, str]]] = defaultdict(list)


def on_config(config: Dict[str, Any]) -> Dict[str, Any]:
    SERIES.clear()
    docs_dir = Path(config["docs_dir"])
    for document in collect_documents(docs_dir):
        series = document.metadata.get("series")
        order = document.metadata.get("order")
        if isinstance(series, str) and isinstance(order, int) and not isinstance(order, bool):
            SERIES[series].append((order, document.relative_path))
    for entries in SERIES.values():
        entries.sort()
    return config


EXCERPT_SEPARATOR = "<!-- more -->"
LEADING_TITLE = re.compile(r"\A\s*#[ \t]+[^\n]*\n+")
FENCE = re.compile(r"^\s*(```|~~~)", re.M)


def add_excerpt_separator(markdown: str) -> str:
    """Cut a blog post's list excerpt after its first paragraph unless the author chose a spot."""
    if EXCERPT_SEPARATOR in markdown:
        return markdown
    blocks = re.split(r"\n[ \t]*\n", markdown.strip("\n"))
    in_fence = False
    for index, block in enumerate(blocks):
        fences = len(FENCE.findall(block))
        starts_inside = in_fence
        in_fence = in_fence ^ (fences % 2 == 1)
        stripped = block.lstrip()
        if starts_inside or fences or stripped.startswith(("#", "<", "!!!", "???", "|")):
            continue
        if index == len(blocks) - 1:
            return markdown
        blocks.insert(index + 1, EXCERPT_SEPARATOR)
        return "\n\n".join(blocks) + "\n"
    return markdown


def on_page_markdown(markdown: str, page: Any, config: Dict[str, Any], files: Any) -> str:
    if page.file.src_uri.startswith("blog/posts/"):
        # The post template prints the frontmatter title, so drop a hand-written "# 标题".
        return add_excerpt_separator(LEADING_TITLE.sub("", markdown, count=1))
    return markdown


def on_nav(nav: Any, config: Dict[str, Any], files: Any) -> Any:
    pages_by_source = {page.file.src_uri: page for page in nav.pages}
    for page in nav.pages:
        page.previous_page = None
        page.next_page = None

    for entries in SERIES.values():
        pages = [pages_by_source[path] for _, path in entries if path in pages_by_source]
        for index, page in enumerate(pages):
            page.previous_page = pages[index - 1] if index > 0 else None
            page.next_page = pages[index + 1] if index + 1 < len(pages) else None
    return nav
