import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from epub3_export import ManifestError, build_epub


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)
NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "xhtml": "http://www.w3.org/1999/xhtml",
}


class EpubExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "images").mkdir()
        (self.root / "images" / "kart.png").write_bytes(PNG_1X1)
        self.manifest_path = self.root / "album.json"
        self.output_path = self.root / "album.epub"

    def tearDown(self):
        self.temp_dir.cleanup()

    def manifest(self):
        return {
            "title": "A Test Album",
            "language": "zh-TW",
            "creator": "Test author",
            "description": "A short demo.",
            "chapters": [
                {
                    "title": "Karts",
                    "items": [
                        {
                            "title": "Blue Kart",
                            "image": "images/kart.png",
                            "alt": "A blue cartoon racing kart viewed from the side.",
                            "caption": "A blue kart.",
                            "source_url": "https://kartarchive.com/?item=123",
                        }
                    ],
                }
            ],
        }

    def write_manifest(self, data):
        self.manifest_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_builds_valid_reflowable_epub3_package(self):
        self.write_manifest(self.manifest())
        build_epub(self.manifest_path, self.output_path)

        with zipfile.ZipFile(self.output_path) as book:
            names = book.namelist()
            self.assertEqual(names[0], "mimetype")
            self.assertEqual(book.read("mimetype"), b"application/epub+zip")
            self.assertEqual(book.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
            package = ElementTree.fromstring(book.read("OEBPS/package.opf"))
            self.assertEqual(package.attrib["version"], "3.0")
            metadata = package.find("opf:metadata", NS)
            self.assertEqual(metadata.find("dc:title", {"dc": "http://purl.org/dc/elements/1.1/"}).text, "A Test Album")
            self.assertEqual(package.find("opf:spine", NS).find("opf:itemref", NS).attrib["idref"], "cover-page")
            nav = ElementTree.fromstring(book.read("OEBPS/nav.xhtml"))
            self.assertIn("Blue Kart", "".join(nav.itertext()))
            chapter = ElementTree.fromstring(book.read("OEBPS/chapter-001.xhtml"))
            image = chapter.find(".//xhtml:img", NS)
            self.assertEqual(image.attrib["alt"], "A blue cartoon racing kart viewed from the side.")
            source_link = chapter.find(".//xhtml:a", NS)
            self.assertEqual(source_link.attrib["href"], "https://kartarchive.com/?item=123")
            self.assertIn("OEBPS/images/image-0001.png", names)
            self.assertIn("reflowable", book.read("OEBPS/package.opf").decode("utf-8"))

    def test_rejects_image_path_outside_manifest_folder(self):
        data = self.manifest()
        data["chapters"][0]["items"][0]["image"] = "../secret.png"
        self.write_manifest(data)
        with self.assertRaisesRegex(ManifestError, "stay inside"):
            build_epub(self.manifest_path, self.output_path)

    def test_rejects_javascript_source_links(self):
        data = self.manifest()
        data["chapters"][0]["items"][0]["source_url"] = "javascript:alert(1)"
        self.write_manifest(data)
        with self.assertRaisesRegex(ManifestError, r"http\(s\) URL"):
            build_epub(self.manifest_path, self.output_path)

    def test_requires_descriptive_alt_text(self):
        data = self.manifest()
        del data["chapters"][0]["items"][0]["alt"]
        self.write_manifest(data)
        with self.assertRaisesRegex(ManifestError, "alt must be a non-empty string"):
            build_epub(self.manifest_path, self.output_path)


if __name__ == "__main__":
    unittest.main()
