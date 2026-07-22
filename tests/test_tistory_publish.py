import tempfile
import unittest
from pathlib import Path

from tistory_newsroom.tistory_publish import prepare_tistory_publish_html


class TistoryPublishTest(unittest.TestCase):
    def _write_package(self, root: Path, image_count: int = 3) -> Path:
        figures = []
        for index in range(image_count):
            name = f"image-{index}.png"
            (root / name).write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([index]))
            figures.append(f'<figure><img src="./{name}" alt="image {index}"></figure>')
        html = root / "article-local-preview.html"
        html.write_text(f"<article>{''.join(figures)}</article>", encoding="utf-8")
        return html

    def test_builds_https_paste_html_and_copies_three_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_package(root)
            assets = root / "docs/assets/post"
            output = root / "article-tistory-paste.html"

            result = prepare_tistory_publish_html(
                source,
                assets,
                "https://example.github.io/blog/assets/post",
                output,
            )

            published = output.read_text(encoding="utf-8")
            self.assertNotIn('src="./', published)
            self.assertIn('src="https://example.github.io/blog/assets/post/cover.png"', published)
            self.assertIn('src="https://example.github.io/blog/assets/post/body-1.png"', published)
            self.assertIn('src="https://example.github.io/blog/assets/post/body-2.png"', published)
            self.assertEqual(source.read_text(encoding="utf-8").count('src="./'), 3)
            self.assertEqual(sorted(path.name for path in assets.iterdir()), ["body-1.png", "body-2.png", "cover.png"])
            self.assertEqual(len(result["image_urls"]), 3)

    def test_rejects_wrong_image_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_package(root, image_count=2)
            with self.assertRaisesRegex(ValueError, "정확히 3개"):
                prepare_tistory_publish_html(source, root / "assets", "https://example.com/assets")

    def test_rejects_non_https_asset_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_package(root)
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                prepare_tistory_publish_html(source, root / "assets", "http://example.com/assets")


if __name__ == "__main__":
    unittest.main()
