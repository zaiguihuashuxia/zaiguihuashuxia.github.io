// 笔记的 collections：「笔记专题」里的每个专题生成一个 collection，对应 public/notes/<文件夹>/。
// 在后台新建、改名、排序专题后保存，刷新本页，左栏就会跟着变；网站构建时读的是同一份列表。
// 这里生成的 collections 会接在 config.yml 里的 collections（博客）后面。

const REPO = "zaiguihuashuxia/zaiguihuashuxia.github.io";
const TOPICS_FILE = "public/notes/topics.json";
const SLUG = "^[a-z0-9]+(-[a-z0-9]+)*$";

const noteFields = [
  { name: "title", label: "标题", widget: "string" },
  { name: "nav_title", label: "导航名", widget: "string", required: false, hint: "左侧导航里显示的短名字，不填就用标题" },
  { name: "description", label: "简介", widget: "string", required: false, hint: "显示在笔记卡片上，不填就用正文的第一段" },
  { name: "order", label: "排序", widget: "number", value_type: "int", required: false, hint: "数字越小越靠前" },
  { name: "series", label: "系列", widget: "string", required: false, hint: "同一系列的笔记会按排序自动串成上一篇、下一篇，这时排序必填" },
  { name: "tags", label: "标签", widget: "list", required: false },
  { name: "comments", label: "评论", widget: "boolean", required: false, default: false, hint: "打开后这一页底部显示评论区" },
  {
    name: "hide",
    label: "隐藏页面元素",
    widget: "select",
    multiple: true,
    required: false,
    options: [
      { label: "左侧导航", value: "navigation" },
      { label: "右侧目录", value: "toc" },
    ],
  },
  { name: "body", label: "正文", widget: "markdown", modes: ["raw", "rich_text"] },
];

// The GitHub token Sveltia saved when you last signed in. GitHub allows 60 requests an hour per
// network without one, which a shared network can use up; with it the limit is 5000.
function savedToken() {
  try {
    const user = JSON.parse(localStorage.getItem("sveltia-cms.user") || "null");
    return typeof user?.token === "string" ? user.token : "";
  } catch {
    return "";
  }
}

// Read the list from GitHub first, so a topic saved a moment ago shows up before the site has
// been rebuilt; fall back to the copy the site publishes.
async function loadTopics() {
  const token = savedToken();
  const headers = { Accept: "application/vnd.github.raw+json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const sources = [
    [`https://api.github.com/repos/${REPO}/contents/${TOPICS_FILE}?ref=main`, { headers }],
    ["../notes/topics.json", {}],
  ];
  for (const [url, options] of sources) {
    try {
      const response = await fetch(url, { ...options, cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!response.ok) continue;
      const data = await response.json();
      if (Array.isArray(data?.topics)) return data.topics;
    } catch (error) {
      console.warn(`读取专题列表失败：${url}`, error);
    }
  }
  return [];
}

// Skip broken entries instead of failing, so the admin still opens and the list can be fixed.
function usableTopics(topics) {
  const seen = new Set();
  return topics.filter((topic) => {
    const ok =
      typeof topic?.folder === "string" &&
      new RegExp(SLUG).test(topic.folder) &&
      !seen.has(topic.folder) &&
      typeof topic.title === "string" &&
      topic.title.trim() !== "";
    if (ok) seen.add(topic.folder);
    else console.warn("跳过有问题的专题：", topic);
    return ok;
  });
}

const topicCollections = usableTopics(await loadTopics()).map((topic) => ({
  name: `topic-${topic.folder}`,
  label: topic.title.trim(),
  label_singular: "笔记",
  description: topic.description || `存放在 public/notes/${topic.folder}/。专题里还能用树下面的 New Folder 再分小文件夹。`,
  icon: topic.icon || "folder",
  folder: `public/notes/${topic.folder}`,
  create: true,
  nested: { depth: 8, subfolders: false },
  meta: { path: {} },
  fields: noteFields,
}));

CMS.init({
  config: {
    collections: [
      { name: "notes-divider", divider: true },
      ...topicCollections,
      {
        name: "notes-loose",
        label: "未分组",
        label_singular: "笔记",
        description: "直接放在笔记最外层、不属于任何专题的笔记，显示在网站左侧目录的最下面。",
        icon: "description",
        folder: "public/notes",
        create: true,
        fields: noteFields,
      },
      { name: "topics-divider", divider: true },
      {
        name: "notes-topics",
        label: "笔记专题",
        icon: "category",
        description: "在这里新建、改名、排序专题。保存后刷新本页，左边的专题就会跟着变；网站的笔记页一两分钟后更新。",
        format: "json",
        files: [
          {
            name: "topics",
            label: "专题列表",
            file: TOPICS_FILE,
            fields: [
              {
                name: "topics",
                label: "专题",
                label_singular: "专题",
                widget: "list",
                summary: "{{fields.title}}（{{fields.folder}}）",
                hint: "拖动可以调整顺序，网站左侧目录按这个顺序排。",
                fields: [
                  { name: "title", label: "名字", widget: "string", hint: "显示在网站左侧目录、笔记卡片和后台左栏，随时可以改" },
                  {
                    name: "folder",
                    label: "文件夹",
                    widget: "string",
                    pattern: [SLUG, "只能用小写英文、数字和连字符"],
                    hint: "笔记存在 public/notes/这个名字/ 里，也是网址的一段，例如 agent。建好后不要再改：改了，原来的笔记不会跟着搬过去",
                  },
                  { name: "description", label: "简介", widget: "string", required: false, hint: "显示在网站的专题卡片和专题页上" },
                  {
                    name: "icon",
                    label: "图标",
                    widget: "string",
                    required: false,
                    hint: "后台左栏的图标，填 Material Symbols 里的名字，例如 smart_toy、code、menu_book；不填就是文件夹",
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
});
