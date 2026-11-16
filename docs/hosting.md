<p align="right">
  <strong>English</strong> ·
  <a href="hosting.zh-CN.md">简体中文</a>
</p>

# How kartarchive.com Is Served

kartarchive.com has about 5 GB of models and textures behind it, and it opens in a browser tab with nothing to install. It runs on one Cloudflare Worker and one R2 bucket, loads only what you open, and still gives search engines and AI answer engines a readable page in every language.

---

## One Worker, One Bucket

The Worker serves the app: the HTML, the scripts and the interface images. The R2 bucket holds the archive itself, about 92,000 files of models, textures, animation data and card pictures, more than static assets can hold. There is no other server. The site answers only on its own domain; `www` redirects to it.

## Only What You Open

The page first loads an index of every card. A card's model, textures and animation data are fetched when you open that card, and each file is checked against the digest the index lists before it is used. Data files are revalidated on every visit, so a new version of the archive shows up on the next load.

## Readable Without JavaScript

The 3D garage needs JavaScript and WebGL. Many readers run neither, including most AI answer engines, so the site also serves plain pages:

- `/catalog/` lists every card on one page with no scripts and no images, with every name the game gives it in the four languages. Every name links to `/?item=<id>`, which opens that card in the garage.
- `/llms.txt` describes the site for language models, and `/llms-full.txt` is the whole catalog in Markdown.
- `/sitemap.xml` lists the home page in four languages and the catalog. `robots.txt` lets every crawler in.

A generator writes these files and the page head from the site's own data, so names and counts cannot drift from what the garage shows. A test fails while any of them is out of date.

## Every Language at One Address

`/` is in Simplified Chinese, the language of the client the archive comes from. `?lang=zh-TW`, `?lang=en` and `?lang=ko` give Traditional Chinese, English and Korean. For those, the Worker rewrites the HTML at the edge with `HTMLRewriter` before it is sent: the language attribute, title, description, canonical link, Open Graph tags, structured data and the no-script text. A crawler that runs no scripts still gets the right language.

Localized responses carry no `ETag` or `Last-Modified`, and conditional request headers are dropped, so a cached copy of one language can never be confirmed as another.

In the browser, the app takes its language from `?lang=`, then from the visitor's saved choice, then Simplified Chinese. It does not follow the browser's language: Google renders pages with an English browser, and the home page declares Simplified Chinese, so the two would disagree.

## Checked Before and After Each Upload

Before an upload, the same Worker code runs locally against a staged copy of the data, and the site is checked there. After the upload, the bucket is read back and compared with the staged copy: every file must be there at the same size, and nothing else may be.
