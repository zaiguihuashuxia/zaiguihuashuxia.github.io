from __future__ import annotations

import unittest
from pathlib import Path


class HomepageTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def test_homepage_exposes_personal_navigation(self) -> None:
        homepage = self.root / "public" / "index.html"
        self.assertTrue(homepage.is_file(), "public/index.html must exist")
        html = homepage.read_text(encoding="utf-8")

        self.assertIn("<title>zaiguihuashuxia", html)
        self.assertIn("<main", html)
        self.assertIn("<h1", html)
        self.assertIn("zaiguihuashuxia", html)
        self.assertIn('href="https://zaiguihuashuxia.github.io/notes/"', html)
        self.assertIn('href="https://github.com/zaiguihuashuxia"', html)
        self.assertNotIn("data-md-component", html)

    def test_homepage_styles_cover_focus_and_mobile_layout(self) -> None:
        stylesheet = self.root / "public" / "styles.css"
        self.assertTrue(stylesheet.is_file(), "public/styles.css must exist")
        css = stylesheet.read_text(encoding="utf-8")

        self.assertIn(":focus-visible", css)
        self.assertIn("@media", css)

    def test_pages_workflow_only_uploads_homepage_public_directory(self) -> None:
        workflow = self.root / ".github" / "workflows" / "pages.yml"
        self.assertTrue(workflow.is_file(), ".github/workflows/pages.yml must exist")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("path: public", text)
        self.assertIn("actions/configure-pages@v5", text)
        self.assertIn("actions/upload-pages-artifact@v4", text)
        self.assertIn("actions/deploy-pages@v4", text)
        self.assertNotIn("scripts/site.py", text)
        self.assertNotIn("mkdocs", text.lower())


if __name__ == "__main__":
    unittest.main()
