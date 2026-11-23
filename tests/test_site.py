from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import markdown

from scripts.site import (
    ContentValidationError,
    build_navigation,
    collect_documents,
    generated_folder_indexes,
    inspect_site,
    note_summary,
    read_document,
    validate_content,
)


class SiteToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_title_is_required(self) -> None:
        self.write("index.md", "# Missing title\n")
        with self.assertRaisesRegex(ContentValidationError, "required frontmatter field 'title'"):
            validate_content(self.root)

    def test_series_requires_integer_order(self) -> None:
        self.write(
            "index.md",
            "---\ntitle: Series page\nseries: demo\n---\n\n# Series page\n",
        )
        with self.assertRaisesRegex(ContentValidationError, "requires an integer 'order'"):
            validate_content(self.root)

    def test_broken_link_identifies_source(self) -> None:
        self.write(
            "guide/index.md",
            "---\ntitle: Guide\n---\n\n[Missing](missing.md)\n",
        )
        with self.assertRaisesRegex(
            ContentValidationError, "guide/index.md: unresolved link or asset 'missing.md'"
        ):
            validate_content(self.root)

    def test_obsidian_only_syntax_is_rejected(self) -> None:
        self.write(
            "index.md",
            "---\ntitle: Obsidian\n---\n\n[[Private note]]\n",
        )
        with self.assertRaisesRegex(ContentValidationError, "wikilinks/transclusions"):
            validate_content(self.root)

    def test_navigation_uses_order_without_changing_paths(self) -> None:
        self.write("index.md", "---\ntitle: Home\norder: 0\n---\n")
        self.write(
            "java/index.md",
            "---\ntitle: Java\nnav_title: Java\norder: 10\n---\n",
        )
        self.write(
            "java/second.md",
            "---\ntitle: Second\nseries: demo\norder: 20\n---\n",
        )
        self.write(
            "java/first.md",
            "---\ntitle: First\nseries: demo\norder: 10\n---\n",
        )
        documents = validate_content(self.root)
        nav = build_navigation(documents, self.root)
        java_items = nav[1]["Java"]
        self.assertEqual(java_items[1], {"First": "java/first.md"})
        self.assertEqual(java_items[2], {"Second": "java/second.md"})

    def test_notes_folders_without_index_still_get_a_page(self) -> None:
        self.write("notes/index.md", "---\ntitle: 笔记\n---\n")
        self.write("notes/展示/小玩意.md", "---\ntitle: 小玩意\nnav_title: gadgets\n---\n")
        self.write("notes/编程/index.md", "---\ntitle: 编程\norder: 1\n---\n")
        self.write("notes/编程/git.md", "---\ntitle: Git\n---\n")
        self.write("notes/编程/python/装饰器.md", "---\ntitle: 装饰器\n---\n")
        self.write("blog/index.md", "---\ntitle: 博客\n---\n")
        self.write("blog/posts/a.md", "---\ntitle: A\ndate: 2026-11-23\nslug: a\n---\n")
        documents = validate_content(self.root)

        nav = build_navigation(documents, self.root)
        self.assertIn({"博客": ["blog/index.md"]}, nav)
        self.assertIn(
            {
                "笔记": [
                    "notes/index.md",
                    {
                        "编程": [
                            "notes/编程/index.md",
                            {"python": ["notes/编程/python/index.md", {"装饰器": "notes/编程/python/装饰器.md"}]},
                            {"Git": "notes/编程/git.md"},
                        ]
                    },
                    {"展示": ["notes/展示/index.md", {"gadgets": "notes/展示/小玩意.md"}]},
                ]
            },
            nav,
        )
        generated = [folder.index_path for folder in generated_folder_indexes(documents, self.root)]
        self.assertEqual(generated, ["notes/展示/index.md", "notes/编程/python/index.md"])

    def test_notes_landing_page_survives_being_deleted(self) -> None:
        self.write("blog/index.md", "---\ntitle: 博客\norder: 5\n---\n")
        self.write("notes/备忘录1.md", "---\ntitle: 备忘录1\nnav_title: memo1\n---\n")
        documents = validate_content(self.root)

        nav = build_navigation(documents, self.root)
        self.assertEqual(
            nav, [{"博客": ["blog/index.md"]}, {"笔记": ["notes/index.md", {"memo1": "notes/备忘录1.md"}]}]
        )
        landing = generated_folder_indexes(documents, self.root)[0]
        self.assertEqual(landing.index_path, "notes/index.md")
        self.assertIn("title: \"笔记\"", landing.generated_markdown())
        self.assertIn("# 笔记", landing.generated_markdown())

    def test_note_summary_prefers_description_then_first_paragraph(self) -> None:
        described = self.write("a.md", "---\ntitle: A\ndescription: 一句话\n---\n\n正文\n")
        self.assertEqual(note_summary(read_document(described, self.root)), "一句话")
        plain = self.write(
            "b.md",
            "---\ntitle: B\n---\n\n# B\n\n```bash\nls\n```\n\n"
            "用 **Git** 管理 `snake_case` 代码，见[文档](https://git-scm.com)。\n\n第二段\n",
        )
        self.assertEqual(
            note_summary(read_document(plain, self.root)), "用 Git 管理 snake_case 代码，见文档。"
        )
        long = self.write("c.md", "---\ntitle: C\n---\n\n" + "字" * 100 + "\n")
        self.assertEqual(note_summary(read_document(long, self.root), limit=10), "字" * 10 + "…")

    def test_blog_post_requires_date_and_slug(self) -> None:
        self.write("blog/posts/no-meta.md", "---\ntitle: 没有日期\n---\n\n正文\n")
        with self.assertRaises(ContentValidationError) as raised:
            validate_content(self.root)
        self.assertIn("requires a 'date'", str(raised.exception))
        self.assertIn("requires a 'slug'", str(raised.exception))

    def test_blog_post_slug_must_be_ascii_and_unique(self) -> None:
        self.write(
            "blog/posts/a.md",
            "---\ntitle: 中文网址\ndate: 2026-11-23\nslug: 你好\n---\n",
        )
        with self.assertRaisesRegex(ContentValidationError, "lowercase letters"):
            validate_content(self.root)
        self.write("blog/posts/a.md", "---\ntitle: A\ndate: 2026-11-23\nslug: hello\n---\n")
        self.write("blog/posts/b.md", "---\ntitle: B\ndate: 2026-11-24\nslug: hello\n---\n")
        with self.assertRaisesRegex(ContentValidationError, "already used"):
            validate_content(self.root)

    def test_valid_blog_post_passes(self) -> None:
        self.write(
            "blog/posts/2026-11-23-hello.md",
            "---\ntitle: 你好\ndate: 2026-11-23\nslug: hello\ncategories:\n  - 随笔\n---\n\n正文\n",
        )
        documents = validate_content(self.root)
        self.assertEqual(len(documents), 1)

    def test_post_excerpt_is_cut_after_first_paragraph(self) -> None:
        import importlib.util

        hook_path = Path(__file__).resolve().parents[1] / "hooks" / "knowledge_library.py"
        spec = importlib.util.spec_from_file_location("knowledge_library", hook_path)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        cut = hook.add_excerpt_separator("# 标题\n\n第一段。\n\n```python\nx = 1\n\ny = 2\n```\n\n第二段。\n")
        self.assertEqual(cut.count("<!-- more -->"), 1)
        self.assertLess(cut.index("第一段"), cut.index("<!-- more -->"))
        self.assertLess(cut.index("<!-- more -->"), cut.index("```python"))
        chosen = "第一段。\n\n第二段。\n\n<!-- more -->\n\n第三段。\n"
        self.assertEqual(hook.add_excerpt_separator(chosen), chosen)
        self.assertEqual(hook.add_excerpt_separator("只有一段。\n"), "只有一段。\n")
        self.assertEqual(hook.LEADING_TITLE.sub("", "# 标题\n\n正文\n", count=1), "正文\n")
        self.assertEqual(hook.LEADING_TITLE.sub("", "正文\n\n# 小节\n", count=1), "正文\n\n# 小节\n")

    def test_artifact_inspection_rejects_private_sentinel(self) -> None:
        self.write("index.html", "PRIVATE_ONLY_SENTINEL")
        search_dir = self.root / "search"
        search_dir.mkdir()
        (search_dir / "search_index.json").write_text(
            json.dumps({"docs": [{"text": "Java 面向对象 Spring Boot IoC"}]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ContentValidationError, "private sentinel"):
            inspect_site(self.root)

    def test_github_pages_deploy_depends_on_successful_build(self) -> None:
        workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "site.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("needs: build", text)
        self.assertIn("uv run python scripts/site.py check", text)
        self.assertIn("path: site", text)
        self.assertIn("actions/deploy-pages@v4", text)

    def test_mkdocs_uses_user_site_production_url(self) -> None:
        config = Path(__file__).resolve().parents[1] / "mkdocs.yml"
        text = config.read_text(encoding="utf-8")
        self.assertIn("site_url: https://zaiguihuashuxia.github.io/\n", text)

    def test_concept_template_renders_supported_structure(self) -> None:
        template = Path(__file__).resolve().parents[1] / "templates" / "concept-note.md"
        document = read_document(template, template.parent)
        rendered = markdown.markdown(
            document.body,
            extensions=["admonition", "tables", "pymdownx.superfences"],
        )
        for heading in ("为什么重要", "核心原理", "最小示例", "常见误区", "自测问题", "相关知识"):
            self.assertIn(heading, rendered)
        self.assertIn("<code", rendered)


if __name__ == "__main__":
    unittest.main()
