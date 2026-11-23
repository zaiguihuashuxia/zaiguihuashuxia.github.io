"""MkDocs hooks: series navigation, blog excerpts and the card listings of notes folders."""

from __future__ import annotations

import json
import posixpath
import re
import sys
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Tuple

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.site import (  # noqa: E402
    FENCE,
    LEADING_TITLE,
    NOTES_DIR_NAME,
    Document,
    collect_documents,
    count_notes,
    generated_folder_indexes,
    list_children,
    note_summary,
)


SERIES: DefaultDict[str, List[Tuple[int, str]]] = defaultdict(list)
DOCUMENTS: Dict[Path, Document] = {}


def on_config(config: Dict[str, Any]) -> Dict[str, Any]:
    SERIES.clear()
    DOCUMENTS.clear()
    docs_dir = Path(config["docs_dir"])
    for document in collect_documents(docs_dir):
        DOCUMENTS[document.path] = document
        series = document.metadata.get("series")
        order = document.metadata.get("order")
        if isinstance(series, str) and isinstance(order, int) and not isinstance(order, bool):
            SERIES[series].append((order, document.relative_path))
    for entries in SERIES.values():
        entries.sort()
    return config


def on_files(files: Any, config: Dict[str, Any]) -> Any:
    """Give every notes folder without an index.md a page, so it can be opened and listed."""
    for folder in generated_folder_indexes(DOCUMENTS.values(), Path(config["docs_dir"])):
        heading = re.sub(r"([\\`*_\[\]#])", r"\\\1", folder.title)
        content = f"---\ntitle: {json.dumps(folder.title, ensure_ascii=False)}\n---\n\n# {heading}\n"
        files.append(File.generated(config, folder.index_path, content=content))
    return files


EXCERPT_SEPARATOR = "<!-- more -->"


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


def _card(kind: str, href: str, title: str, text: str, count: str = "") -> str:
    count_html = f'<span class="zg-card__count">{escape(count)}</span>' if count else ""
    text_html = f'<p class="zg-card__text">{escape(text)}</p>' if text else ""
    return (
        f'<article class="zg-card zg-card--{kind}">'
        f'<p class="zg-card__title"><a href="{escape(href)}">{escape(title)}</a>{count_html}</p>'
        f"{text_html}</article>"
    )


def folder_listing(src_uri: str, docs_dir: Path, files: Any) -> str:
    """Cards for the subfolders and notes of the folder whose index page is src_uri."""
    folders, notes = list_children(docs_dir / posixpath.dirname(src_uri), DOCUMENTS, docs_dir)
    page_file = files.get_file_from_path(src_uri)
    cards = []
    for folder in folders:
        target = files.get_file_from_path(folder.index_path)
        if target is None:
            continue
        total = count_notes(folder, DOCUMENTS)
        cards.append(
            _card(
                "folder",
                target.url_relative_to(page_file),
                folder.title,
                folder.description,
                f"{total} 篇" if total else "空",
            )
        )
    for note in notes:
        target = files.get_file_from_path(note.relative_path)
        if target is None:
            continue
        cards.append(_card("note", target.url_relative_to(page_file), note.title, note_summary(note)))
    if cards:
        return f'<div class="zg-cards">{"".join(cards)}</div>'
    if src_uri != f"{NOTES_DIR_NAME}/index.md":
        return '<p class="zg-empty">这个文件夹里还没有笔记。</p>'
    return ""


def on_page_content(html: str, page: Any, config: Dict[str, Any], files: Any) -> str:
    src_uri = page.file.src_uri
    if src_uri.startswith(f"{NOTES_DIR_NAME}/") and posixpath.basename(src_uri) == "index.md":
        return html + folder_listing(src_uri, Path(config["docs_dir"]), files)
    return html


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
