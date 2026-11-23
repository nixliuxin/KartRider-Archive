# EPUB 3 Album Export

The repository does not include the garage website's source code or the archive's game data. This optional, dependency-free utility turns a **user-curated set of local screenshots or renders** into a portable EPUB 3 album; it does not scrape the site or extract game assets.

The generated book uses a reflowable layout so readers can change text size and margins. It includes a cover, an in-book contents page, chapter navigation, alt text for every image, captions, and optional links back to source cards. Images are packaged locally so the book can be read offline. JPEG and PNG are supported for broad reader compatibility.

## 1. Prepare an album folder

Create an `album.json` file and put the selected images inside the same folder. Each image needs descriptive `alt` text; this is used by screen readers and shown if the image cannot be displayed.

```text
my-album/
  album.json
  images/
    cover.jpg
    kart-01.png
```

Example `album.json`:

```json
{
  "title": "Kart Archive — My Album",
  "language": "zh-TW",
  "creator": "Your name",
  "description": "A small selection of favorite cards.",
  "cover": "images/cover.jpg",
  "chapters": [
    {
      "title": "Karts",
      "items": [
        {
          "title": "Blue Kart",
          "image": "images/kart-01.png",
          "alt": "A blue cartoon racing kart viewed from the side.",
          "caption": "A short caption, if desired.",
          "source_url": "https://kartarchive.com/?item=123"
        }
      ]
    }
  ]
}
```

`cover` is optional; if omitted, the first album image is used. `creator`, `description`, `caption`, and `source_url` are optional. `language` is a BCP 47 tag such as `en`, `zh-CN`, `zh-TW`, or `ko`. If there is only one section, an `items` array can be used at the root instead of `chapters`.

## 2. Export

Python 3.9 or newer is required; no third-party packages are used.

```sh
python tools/epub3_export.py my-album/album.json --output my-album/kart-album.epub
```

The export validates the manifest and image paths, writes the EPUB 3 package, and checks its XML and archive structure. You can then sideload the `.epub` file into an EPUB reader. An optional compatibility check with [EPUBCheck](https://github.com/w3c/epubcheck) is also recommended before distributing a book.

## Notes

- The exporter packages only the images and text you choose; it does not download content from `kartarchive.com`.
- A 3D scene or animation must first be captured as a still image. The EPUB remains an offline photo album, not an interactive 3D viewer.
- Repository text is CC BY 4.0, but the game artwork is not covered by that license. Confirm rights before distributing a book containing game artwork.
