from __future__ import annotations

import unittest
from pathlib import Path


class HomepageTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def test_homepage_links_to_blog_notes_and_github(self) -> None:
        homepage = self.root / "public" / "index.html"
        self.assertTrue(homepage.is_file(), "public/index.html must exist")
        html = homepage.read_text(encoding="utf-8")

        self.assertIn("<title>zaiguihuashuxia", html)
        self.assertIn("<main", html)
        self.assertIn("<h1", html)
        self.assertIn('href="https://zaiguihuashuxia.github.io/blog/"', html)
        self.assertIn('href="https://zaiguihuashuxia.github.io/notes/"', html)
        self.assertIn('href="https://github.com/zaiguihuashuxia"', html)
        self.assertNotIn("zaiguihuashuxia.github.io/notes/blog", html)

    def test_homepage_styles_cover_focus_and_mobile_layout(self) -> None:
        html = (self.root / "public" / "index.html").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", html)
        self.assertIn("@media", html)

    def test_homepage_artwork_is_published(self) -> None:
        for name in ("banner-day.svg", "banner-night.svg", "osmanthus.svg", "bunny.svg"):
            self.assertTrue((self.root / "public" / "assets" / name).is_file(), name)

    def test_single_pages_workflow_builds_the_whole_site(self) -> None:
        workflows = self.root / ".github" / "workflows"
        self.assertEqual(sorted(path.name for path in workflows.glob("*.yml")), ["site.yml"])


if __name__ == "__main__":
    unittest.main()
