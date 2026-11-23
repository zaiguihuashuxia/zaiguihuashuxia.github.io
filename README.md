<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./public/assets/banner-night.svg">
  <img src="./public/assets/banner-day.svg" width="100%" alt="像素画：杭州湖边，一棵开花的桂花树下，戴圆框眼镜的我抱着电脑写代码，旁边蹲着一只小白兔">
</picture>

# zaiguihuashuxia 的个人站点

<https://zaiguihuashuxia.github.io/> 的全部源码：

| 网址 | 内容 | 源文件 |
| --- | --- | --- |
| `/` | GitHub 式的主页 | `public/index.html`（手写，原样发布） |
| `/blog/` | 博客 | `public/blog/`，文章在 `public/blog/posts/` |
| `/notes/` | 学习笔记 | `public/notes/`，每个专题一个文件夹，专题列表在 `public/notes/topics.json` |
| `/admin/` | 写作后台 | `public/admin/`（[Sveltia CMS](https://sveltiacms.app/)） |

博客和笔记用 Material for MkDocs 构建，外观和主页统一；文章下面的评论由 [giscus](https://giscus.app/) 存在本仓库的 Discussions 里。主页的贡献格子图由浏览器从 [github-contributions-api](https://github.com/grubersjoe/github-contributions-api) 实时读取。 `public/` 的内容是公开的。

## 在网页上写作

打开 <https://zaiguihuashuxia.github.io/admin/>，点「使用访问令牌登录」。写完点保存，后台会直接向 `main` 分支提交一次，GitHub Actions 检查并构建，通过后一两分钟上线。

访问令牌在 <https://github.com/settings/personal-access-tokens/new> 生成：**Repository access** 只选 `zaiguihuashuxia.github.io`，**Repository permissions → Contents** 选 *Read and write*，其他都不用开。令牌只保存在当前浏览器里；不用了或丢了，就在 GitHub 的令牌页面撤销。登录页上的「使用 GitHub 登录」需要另外部署 OAuth 服务，这里没有配置。

## 博客文章的格式

后台会自动填好这些字段；在本地手写时注意：

```markdown
---
title: 文章标题
slug: first-post        # 网址的最后一段：小写英文、数字和连字符，不能和别的文章重复
date: 2026-11-23
description: 一句话摘要  # 可选
draft: true             # 可选，草稿不会发布
comments: false         # 可选，关掉这篇的评论区
---

正文。列表页只显示第一段；想自己决定截到哪里，就单独写一行 <!-- more -->
```

文章会发布在 `/blog/年/月/slug/`。

## 笔记的专题

笔记按专题分，每个专题是 `public/notes/` 下的一个文件夹，在后台是左栏里的一个 collection，在网站上是笔记页左侧目录的第一层。专题列表存在 `public/notes/topics.json`，后台和网站都按它来，所以只在后台改就行：

1. 后台左栏点「笔记专题」→「专题列表」，**添加 专题**，填名字（中文也行，随时可以改）和文件夹（小写英文、数字和连字符，也是网址的一段）。拖动可以调整顺序，保存。
2. 刷新后台，左栏就多出这个专题；网站一两分钟后也会出现它，没有笔记时显示「空」。
3. 在专题里点 **New** 写笔记。专题里还想再分小组，就用树下面的 **New Folder**，文件夹要等里面保存了第一篇笔记才会真正出现在仓库里。

注意：专题建好后别改「文件夹」，改了原来的笔记不会跟着搬；删专题前先把里面的笔记删掉或挪走，不然这些笔记在网站上还在（用文件夹名显示），后台里却找不到了。不属于任何专题的笔记放在「未分组」，显示在左侧目录的最下面。

后台的笔记 collections 由 `public/admin/notes.js` 按专题列表生成（博客在 `config.yml`）。它先用你登录后台时保存的令牌从 GitHub 读最新的列表，读不到就用网站上发布的那份，这时新专题要等网站更新完才会出现。

卡片上的说明取笔记的「简介」，不填就用正文第一段。专题里的小文件夹默认用文件夹名当标题；想给它换标题、加简介、调排序，就在文件夹里放一个写好 `title`、`description`、`order` 的 `index.md`。笔记首页 `/notes/` 也一样：`public/notes/index.md` 删掉后会自动生成一个默认首页。笔记页默认没有评论区，需要的话打开「评论」。

## 本地运行

需要 Python 3.9+ 和 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --frozen
uv run python scripts/site.py serve   # 本地预览
uv run python scripts/site.py check   # 测试、严格构建和发布前检查
```

构建结果在 `site/`，不提交 Git。`main` 分支的每次提交都会由 GitHub Actions 检查并部署；检查不通过时网站保持原样，原因可以在仓库的 Actions 页面看到。

> less is more
