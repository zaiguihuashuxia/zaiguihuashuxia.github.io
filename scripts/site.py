#!/usr/bin/env python3
"""Validate, configure, build, inspect, and serve the public knowledge site."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote

import yaml


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"
BASE_CONFIG = ROOT / "mkdocs.yml"
GENERATED_DIR = ROOT / ".generated"
GENERATED_CONFIG = GENERATED_DIR / "mkdocs.yml"
SITE_DIR = ROOT / "site"

FRONTMATTER_DELIMITER = "---"
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
OBSIDIAN_LINK = re.compile(r"!?\[\[[^\]]+\]\]")
OBSIDIAN_BLOCK_ID = re.compile(r"(?m)(?:^|\s)\^[A-Za-z0-9-]+\s*$")
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:")
PRIVATE_SENTINELS = (
    "PRIVATE_ONLY_SENTINEL",
    "DRAFT_ONLY_SENTINEL",
    "PRIVATE_ASSET_SENTINEL",
    ".obsidian/workspace",
)
SEARCH_TERMS = ("博客", "笔记")
BLOG_POSTS_PREFIX = "blog/posts/"
NOTES_DIR_NAME = "notes"
NOTES_TITLE = "笔记"
NOTES_INTRO = "按主题整理的学习笔记，整理好一篇放一篇。"
# The notes topics, edited in the writing admin where each one is a collection (admin/notes.js).
TOPICS_FILE = f"{NOTES_DIR_NAME}/topics.json"
HOMEPAGE_URL = "https://zaiguihuashuxia.github.io/"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LEADING_TITLE = re.compile(r"\A\s*#[ \t]+[^\n]*\n+")
FENCE = re.compile(r"^\s*(```|~~~)", re.M)
SUMMARY_LENGTH = 80
DEFAULT_ORDER = 10_000


class ContentValidationError(RuntimeError):
    """Raised when public content violates the publication contract."""


@dataclass(frozen=True)
class Document:
    path: Path
    relative_path: str
    metadata: Dict[str, Any]
    body: str

    @property
    def title(self) -> str:
        return str(self.metadata["title"])

    @property
    def nav_title(self) -> str:
        return str(self.metadata.get("nav_title", self.title))

    @property
    def order(self) -> int:
        value = self.metadata.get("order", DEFAULT_ORDER)
        return value if isinstance(value, int) and not isinstance(value, bool) else DEFAULT_ORDER

    @property
    def description(self) -> str:
        value = self.metadata.get("description")
        return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class Topic:
    """One entry of notes/topics.json: a top-level notes folder with its name and blurb."""

    folder: str
    title: str
    description: str
    order: int


@dataclass(frozen=True)
class Folder:
    """A folder of notes; its index.md is optional and only adds a title and an intro.

    A topic folder takes its name, blurb and place from notes/topics.json instead, and exists
    even before the repository has a folder for it.
    """

    path: Path
    relative_path: str
    index: Optional[Document]
    topic: Optional[Topic] = None

    @property
    def index_path(self) -> str:
        return f"{self.relative_path}/index.md"

    @property
    def is_notes_root(self) -> bool:
        return self.relative_path == NOTES_DIR_NAME

    @property
    def title(self) -> str:
        if self.topic:
            return self.topic.title
        if self.index:
            return self.index.title
        return NOTES_TITLE if self.is_notes_root else self.path.name

    @property
    def nav_title(self) -> str:
        if self.topic:
            return self.topic.title
        return self.index.nav_title if self.index else self.title

    @property
    def order(self) -> int:
        if self.topic:
            return self.topic.order
        return self.index.order if self.index else DEFAULT_ORDER

    @property
    def description(self) -> str:
        if self.topic and self.topic.description:
            return self.topic.description
        return self.index.description if self.index else ""

    def generated_markdown(self) -> str:
        """The page the build uses for this folder while it has no index.md of its own."""
        heading = re.sub(r"([\\`*_\[\]#])", r"\\\1", self.title)
        intro = NOTES_INTRO if self.is_notes_root else self.description
        intro_block = f"\n{intro}\n" if intro else ""
        return f"---\ntitle: {json.dumps(self.title, ensure_ascii=False)}\n---\n\n# {heading}\n{intro_block}"


def load_topics(public_dir: Path = PUBLIC_DIR) -> List[Topic]:
    """The notes topics in the order the writing admin lists them; none without the file."""
    path = public_dir / TOPICS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContentValidationError(f"{TOPICS_FILE}: not valid JSON ({error})") from error
    items = data.get("topics", []) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ContentValidationError(f"{TOPICS_FILE}: expected an object with a 'topics' list")

    topics: List[Topic] = []
    errors: List[str] = []
    seen: Dict[str, int] = {}
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"{TOPICS_FILE}: topic {position} is not an object")
            continue
        folder, title, description = item.get("folder"), item.get("title"), item.get("description")
        if not isinstance(folder, str) or not SLUG.match(folder):
            errors.append(
                f"{TOPICS_FILE}: topic {position} needs a 'folder' of lowercase letters, digits "
                "and hyphens, such as agent"
            )
        elif folder in seen:
            errors.append(f"{TOPICS_FILE}: topics {seen[folder]} and {position} share the folder '{folder}'")
        elif not isinstance(title, str) or not title.strip():
            errors.append(f"{TOPICS_FILE}: topic {position} ('{folder}') needs a 'title'")
        else:
            seen[folder] = position
            text = description.strip() if isinstance(description, str) else ""
            topics.append(Topic(folder, title.strip(), text, position))
    if errors:
        raise ContentValidationError("\n".join(errors))
    return topics


def read_document(path: Path, public_dir: Path = PUBLIC_DIR) -> Document:
    text = path.read_text(encoding="utf-8")
    metadata: Dict[str, Any] = {}
    body = text
    if text.startswith(f"{FRONTMATTER_DELIMITER}\n"):
        parts = text.split(f"\n{FRONTMATTER_DELIMITER}\n", 1)
        if len(parts) != 2:
            raise ContentValidationError(f"{path}: frontmatter is not terminated with ---")
        raw_metadata = parts[0][len(FRONTMATTER_DELIMITER) + 1 :]
        parsed = yaml.safe_load(raw_metadata) or {}
        if not isinstance(parsed, dict):
            raise ContentValidationError(f"{path}: frontmatter must be a YAML mapping")
        metadata = parsed
        body = parts[1]
    try:
        relative_path = path.relative_to(public_dir).as_posix()
    except ValueError:
        relative_path = path.name
    return Document(path, relative_path, metadata, body)


def collect_documents(public_dir: Path = PUBLIC_DIR) -> List[Document]:
    if not public_dir.is_dir():
        raise ContentValidationError(f"Public source directory does not exist: {public_dir}")
    return [read_document(path, public_dir) for path in sorted(public_dir.rglob("*.md"))]


def _link_destination(raw_target: str) -> str:
    target = raw_target.strip()
    if " " in target and not target.startswith("<"):
        target = target.split(" ", 1)[0]
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return unquote(target.split("#", 1)[0])


def _candidate_paths(source: Path, destination: str, public_dir: Path) -> Iterable[Path]:
    base = public_dir if destination.startswith("/") else source.parent
    target = base / destination.lstrip("/")
    yield target
    if destination.endswith("/"):
        yield target / "index.md"
    elif not target.suffix:
        yield target.with_suffix(".md")
        yield target / "index.md"


def validate_content(public_dir: Path = PUBLIC_DIR) -> List[Document]:
    documents = collect_documents(public_dir)
    errors: List[str] = []
    series_orders: Dict[Tuple[str, int], str] = {}
    post_slugs: Dict[str, str] = {}
    try:
        load_topics(public_dir)
    except ContentValidationError as error:
        errors.append(str(error))

    for document in documents:
        title = document.metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{document.relative_path}: required frontmatter field 'title' is missing")

        series = document.metadata.get("series")
        order = document.metadata.get("order")
        if series is not None:
            if not isinstance(series, str) or not series.strip():
                errors.append(f"{document.relative_path}: 'series' must be a non-empty string")
            if not isinstance(order, int) or isinstance(order, bool):
                errors.append(
                    f"{document.relative_path}: ordered series article requires an integer 'order'"
                )
            else:
                key = (str(series), order)
                if key in series_orders:
                    errors.append(
                        f"{document.relative_path}: duplicate order {order} in series '{series}' "
                        f"(also used by {series_orders[key]})"
                    )
                series_orders[key] = document.relative_path

        if document.relative_path.startswith(BLOG_POSTS_PREFIX):
            errors.extend(_validate_post(document, post_slugs))

        if OBSIDIAN_LINK.search(document.body):
            errors.append(
                f"{document.relative_path}: Obsidian wikilinks/transclusions are not supported"
            )
        if OBSIDIAN_BLOCK_ID.search(document.body):
            errors.append(f"{document.relative_path}: Obsidian block IDs are not supported")

        for match in MARKDOWN_LINK.finditer(document.body):
            destination = _link_destination(match.group(1))
            if not destination or destination.startswith("#") or destination.startswith(EXTERNAL_SCHEMES):
                continue
            if any(candidate.exists() for candidate in _candidate_paths(document.path, destination, public_dir)):
                continue
            errors.append(
                f"{document.relative_path}: unresolved link or asset '{destination}'"
            )

    if errors:
        raise ContentValidationError("\n".join(errors))
    return documents


def _validate_post(document: Document, seen_slugs: Dict[str, str]) -> List[str]:
    """Blog posts need a date for the blog plugin and an ASCII slug for a stable URL."""
    errors: List[str] = []
    created = document.metadata.get("date")
    if isinstance(created, dict):
        created = created.get("created")
    if not isinstance(created, date):
        errors.append(f"{document.relative_path}: blog post requires a 'date' such as 2026-11-23")
    slug = document.metadata.get("slug")
    if not isinstance(slug, str) or not SLUG.match(slug):
        errors.append(
            f"{document.relative_path}: blog post requires a 'slug' of lowercase letters, "
            "digits and hyphens, such as first-post"
        )
    elif slug in seen_slugs:
        errors.append(
            f"{document.relative_path}: slug '{slug}' is already used by {seen_slugs[slug]}"
        )
    else:
        seen_slugs[slug] = document.relative_path
    return errors


def _sort_key(item: Any) -> Tuple[int, str]:
    return item.order, item.nav_title.casefold()


def _is_notes_folder(directory: Path, public_dir: Path) -> bool:
    try:
        parts = directory.relative_to(public_dir).parts
    except ValueError:
        return False
    return len(parts) >= 1 and parts[0] == NOTES_DIR_NAME


def _contains_documents(directory: Path, by_path: Dict[Path, Document]) -> bool:
    return any(directory in path.parents for path in by_path)


def list_children(
    directory: Path,
    by_path: Dict[Path, Document],
    public_dir: Path = PUBLIC_DIR,
    topics: Sequence[Topic] = (),
) -> Tuple[List[Folder], List[Document]]:
    """Subfolders, then pages, of one folder, each sorted by order and then name.

    Outside notes/ a subfolder needs an index.md to count; inside notes/ any folder holding a
    note counts, because the writing admin creates folders without one. In notes/ itself every
    topic counts, first and in the admin's order, even before its first note is saved.
    """
    unplaced = {topic.folder: topic for topic in topics} if directory == public_dir / NOTES_DIR_NAME else {}
    folders: List[Folder] = []
    pages: List[Document] = []
    if directory.is_dir():
        for child_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
            topic = unplaced.pop(child_dir.name, None)
            index = by_path.get(child_dir / "index.md")
            if index is None and topic is None and not (
                _is_notes_folder(child_dir, public_dir) and _contains_documents(child_dir, by_path)
            ):
                continue
            folders.append(Folder(child_dir, child_dir.relative_to(public_dir).as_posix(), index, topic))
        pages = [
            by_path[path]
            for path in sorted(directory.glob("*.md"))
            if path.name != "index.md" and path in by_path
        ]
    folders.extend(
        Folder(path, path.relative_to(public_dir).as_posix(), None, topic)
        for path, topic in ((directory / folder, topic) for folder, topic in unplaced.items())
    )
    return sorted(folders, key=_sort_key), sorted(pages, key=_sort_key)


def generated_folder_indexes(
    documents: Iterable[Document], public_dir: Path = PUBLIC_DIR
) -> List[Folder]:
    """Notes folders and topics without an index.md; the build gives each a listing page.

    The notes landing page is always among them when missing, so deleting it in the writing
    admin cannot take /notes/ off the site.
    """
    by_path = {document.path: document for document in documents}
    notes_dir = public_dir / NOTES_DIR_NAME
    topics = {notes_dir / topic.folder: topic for topic in load_topics(public_dir)}
    folders = {notes_dir, *topics}
    for path in by_path:
        for parent in path.parents:
            if parent == notes_dir or notes_dir not in parent.parents:
                break
            folders.add(parent)
    return [
        Folder(folder, folder.relative_to(public_dir).as_posix(), None, topics.get(folder))
        for folder in sorted(folders)
        if folder / "index.md" not in by_path
    ]


def count_notes(folder: Folder, by_path: Dict[Path, Document]) -> int:
    return sum(1 for path in by_path if folder.path in path.parents and path.name != "index.md")


def _plain_text(markdown_text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown_text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*+]|\d+\.|>)\s+", "", text)
    text = re.sub(r"\*\*|__|~~|`|(?<!\w)[*_]|[*_](?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def note_summary(document: Document, limit: int = SUMMARY_LENGTH) -> str:
    """The note's description, or else the start of its first paragraph."""
    if document.description:
        return document.description
    body = LEADING_TITLE.sub("", document.body, count=1)
    in_fence = False
    for block in re.split(r"\n[ \t]*\n", body.strip()):
        fences = len(FENCE.findall(block))
        starts_inside = in_fence
        in_fence = in_fence ^ (fences % 2 == 1)
        stripped = block.strip()
        if starts_inside or fences or stripped.startswith(("#", "<", "!!!", "???", "|", "$$")):
            continue
        text = _plain_text(stripped)
        if text:
            return text if len(text) <= limit else text[:limit].rstrip() + "…"
    return ""


def _build_directory_nav(
    directory: Path,
    by_path: Dict[Path, Document],
    public_dir: Path = PUBLIC_DIR,
    topics: Sequence[Topic] = (),
) -> List[Any]:
    items: List[Any] = []
    if (directory / "index.md") in by_path or _is_notes_folder(directory, public_dir):
        items.append(f"{directory.relative_to(public_dir).as_posix()}/index.md")
    folders, pages = list_children(directory, by_path, public_dir, topics)
    items.extend(
        {folder.nav_title: _build_directory_nav(folder.path, by_path, public_dir, topics)}
        for folder in folders
    )
    items.extend({page.nav_title: page.relative_path} for page in pages)
    return items


def build_navigation(documents: Sequence[Document], public_dir: Path = PUBLIC_DIR) -> List[Any]:
    by_path = {document.path: document for document in documents}
    topics = load_topics(public_dir)
    nav: List[Any] = []
    root_index = public_dir / "index.md"
    if root_index in by_path:
        nav.append({by_path[root_index].nav_title: by_path[root_index].relative_path})

    sections = [
        Folder(path, path.name, by_path[path / "index.md"])
        for path in public_dir.iterdir()
        if path.is_dir() and (path / "index.md") in by_path
    ]
    notes_dir = public_dir / NOTES_DIR_NAME
    if not any(section.path == notes_dir for section in sections):
        sections.append(Folder(notes_dir, NOTES_DIR_NAME, None))
    for section in sorted(sections, key=_sort_key):
        nav.append({section.nav_title: _build_directory_nav(section.path, by_path, public_dir, topics)})
    return nav


def generate_config(documents: Sequence[Document]) -> Path:
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    config["docs_dir"] = str(PUBLIC_DIR)
    config["site_dir"] = str(SITE_DIR)
    # The site root is the hand-written homepage (public/index.html), linked as the first tab.
    config["nav"] = [{"主页": HOMEPAGE_URL}, *build_navigation(documents)]
    config["hooks"] = [str(ROOT / "hooks" / "knowledge_library.py")]
    theme = config.get("theme")
    if isinstance(theme, dict) and theme.get("custom_dir"):
        theme["custom_dir"] = str(ROOT / theme["custom_dir"])
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_CONFIG.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return GENERATED_CONFIG


def _mkdocs_executable() -> str:
    candidate = Path(sys.executable).with_name("mkdocs")
    return str(candidate) if candidate.exists() else "mkdocs"


def run_mkdocs(arguments: Sequence[str]) -> None:
    subprocess.run([_mkdocs_executable(), *arguments], cwd=ROOT, check=True)


def inspect_site(site_dir: Path = SITE_DIR) -> None:
    if not site_dir.is_dir():
        raise ContentValidationError(f"Generated site does not exist: {site_dir}")
    text_files = [
        path
        for path in site_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".json", ".js", ".css", ".xml", ".txt"}
    ]
    forbidden_path_parts = {"private", "drafts", "private-assets", ".obsidian"}
    leaked_paths = [
        str(path.relative_to(site_dir))
        for path in site_dir.rglob("*")
        if path.is_file() and forbidden_path_parts.intersection(path.relative_to(site_dir).parts)
    ]
    if leaked_paths:
        raise ContentValidationError(
            f"Generated artifact contains local-only path(s): {', '.join(leaked_paths)}"
        )
    combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in text_files)
    leaks = [token for token in PRIVATE_SENTINELS if token in combined]
    if leaks:
        raise ContentValidationError(f"Generated artifact contains private sentinel(s): {', '.join(leaks)}")

    search_index = site_dir / "search" / "search_index.json"
    if not search_index.is_file():
        raise ContentValidationError("Generated site is missing local search index")
    search_data = json.loads(search_index.read_text(encoding="utf-8"))
    search_text = json.dumps(search_data, ensure_ascii=False).replace("\u200b", "")
    missing_terms = [term for term in SEARCH_TERMS if term not in search_text]
    if missing_terms:
        raise ContentValidationError(
            f"Search index is missing representative term(s): {', '.join(missing_terms)}"
        )

    search_locations = [str(item.get("location", "")) for item in search_data.get("docs", [])]
    if not any(location.startswith("blog/") for location in search_locations):
        raise ContentValidationError("Search index is missing blog pages")

    home_page = site_dir / "index.html"
    blog_page = site_dir / "blog" / "index.html"
    notes_page = site_dir / "notes" / "index.html"
    required_files = (
        home_page,
        blog_page,
        notes_page,
        site_dir / "admin" / "index.html",
        site_dir / "admin" / "config.yml",
        site_dir / "404.html",
    )
    for required_file in required_files:
        if not required_file.is_file():
            raise ContentValidationError(f"Generated site is missing required file: {required_file}")

    home_html = home_page.read_text(encoding="utf-8")
    homepage_fragments = ("<title>zaiguihuashuxia</title>", "assets/banner-day.svg", 'href="https://zaiguihuashuxia.github.io/blog/"')
    missing_home = [fragment for fragment in homepage_fragments if fragment not in home_html]
    if missing_home:
        raise ContentValidationError(
            f"Homepage was not copied as-is; missing fragment(s): {', '.join(missing_home)}"
        )

    blog_html = blog_page.read_text(encoding="utf-8")
    theme_fragments = ('data-md-color-scheme="default"', 'data-md-color-scheme="slate"')
    missing_fragments = [fragment for fragment in theme_fragments if fragment not in blog_html]
    if missing_fragments:
        raise ContentValidationError(
            f"Blog page is missing theme fragment(s): {', '.join(missing_fragments)}"
        )
    if "md-footer__link" in notes_page.read_text(encoding="utf-8"):
        raise ContentValidationError("Standalone page received artificial previous/next navigation")


def run_unit_tests() -> None:
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


def build(strict: bool = True) -> None:
    documents = validate_content()
    config_path = generate_config(documents)
    arguments = ["build", "--config-file", str(config_path)]
    if strict:
        arguments.append("--strict")
    run_mkdocs(arguments)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "build", "inspect", "check", "serve"))
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            documents = validate_content()
            generate_config(documents)
            print(f"Validated {len(documents)} public Markdown files")
        elif args.command == "build":
            build(strict=True)
            print(f"Built static site at {SITE_DIR}")
        elif args.command == "inspect":
            inspect_site()
            print("Generated artifact passed privacy and search inspection")
        elif args.command == "check":
            run_unit_tests()
            build(strict=True)
            inspect_site()
            print("All knowledge-site checks passed")
        elif args.command == "serve":
            documents = validate_content()
            config_path = generate_config(documents)
            try:
                run_mkdocs(("serve", "--config-file", str(config_path)))
            except KeyboardInterrupt:
                print("Preview stopped")
    except (ContentValidationError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
