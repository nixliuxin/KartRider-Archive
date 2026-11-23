# EPUB 3 画册导出

本仓库不包含车库网站的源代码或档案中的游戏数据。本工具不依赖第三方库，可将**用户自行整理的本地截图或渲染图**打包为 EPUB 3 电子画册；它不会抓取网站，也不会提取游戏资源。

生成的电子书采用可重排版式，读者可调整字号和边距。书内含封面、目录、章节导航、每张图片的替代文本、说明文字，以及可选的原卡片链接。图片会打包进电子书，方便离线阅读。为兼容更多阅读器，支持 JPEG 和 PNG。

## 1. 准备画册文件夹

创建 `album.json`，并把选好的图片放在同一文件夹内。每张图片都需要有描述性的 `alt` 替代文本，供屏幕阅读器朗读，也可在图片无法显示时提供说明。

```text
my-album/
  album.json
  images/
    cover.jpg
    kart-01.png
```

`album.json` 示例：

```json
{
  "title": "跑跑档案馆——我的画册",
  "language": "zh-CN",
  "creator": "你的名字",
  "description": "精选的几张卡片。",
  "cover": "images/cover.jpg",
  "chapters": [
    {
      "title": "卡丁车",
      "items": [
        {
          "title": "蓝色卡丁车",
          "image": "images/kart-01.png",
          "alt": "一辆蓝色卡通赛车的侧面图。",
          "caption": "可选的简短说明。",
          "source_url": "https://kartarchive.com/?item=123"
        }
      ]
    }
  ]
}
```

`cover` 可省略；省略时会使用画册中的第一张图片。`creator`、`description`、`caption` 和 `source_url` 均为可选项。`language` 使用 BCP 47 语言标签，例如 `en`、`zh-CN`、`zh-TW` 或 `ko`。如果只有一个章节，也可以在根对象中直接提供 `items` 数组，而不使用 `chapters`。

## 2. 导出

需要 Python 3.9 或更新版本；不需要安装第三方套件。

```sh
python tools/epub3_export.py my-album/album.json --output my-album/kart-album.epub
```

导出时会验证清单和图片路径，生成 EPUB 3 文件，并检查 XML 与压缩包结构。之后可将 `.epub` 文件导入电子书阅读器。正式发布前也建议用 [EPUBCheck](https://github.com/w3c/epubcheck) 做兼容性检查。

## 说明

- 工具只打包你选择的图片和文字，不会从 `kartarchive.com` 下载内容。
- 3D 场景或动画须先截取为静态图；生成的 EPUB 是离线画册，不是互动 3D 查看器。
- 仓库文字使用 CC BY 4.0 授权，但此授权不涵盖游戏美术。分发含游戏美术的电子书前，请先确认相关权利。
