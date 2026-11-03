# 咸鱼自动上货 + 新浪体育资讯抓取

基于 **Tkinter + Playwright** 的桌面小工具，两个独立 Tab：

- **上货**：半自动闲鱼（goofish）PC 端上货。登录与最终发布由人工完成，脚本负责打开首页 → 点击「发闲置」→ 发布页 → 上传首图 → 填写描述/价格/原价。
- **资讯抓取**：只读抓取新浪体育（首页 + 滚动新闻列表），提取标题 / 链接 / 时间 / 正文，按天落盘到 `data/news/YYYY-MM-DD.json`，支持去重、限速与每天定时。

两者共享同一套执行机制（工作线程 + 命令队列 + 日志），但各自使用独立的浏览器上下文和用户数据目录，互不影响。

## 功能

| 能力 | 上货 | 资讯抓取 |
| --- | --- | --- |
| 复用本机浏览器 | ✅ channel 启动本机 Chrome/Edge，不下载 playwright 浏览器 | ✅ 同一机制，headless 无窗口 |
| 登录态 | 独立 `browser_profile/`，登录一次长期复用 | 不需要登录，独立 `news_profile/` |
| 自动化步骤 | 发闲置 → 发布页 → 首图 → 描述/价格/原价 | 列表页取链接 → 正文页取内容 |
| 输出 | 页面填好，人工点发布 | 按天写 JSON，去重 + 限速 |
| 触发方式 | GUI 按钮 | GUI 按钮 / 每天定时 / `--job news` 命令行 |
| 日志 | `[上货]` 前缀 | `[资讯]` 前缀，可按来源过滤 |

## 环境要求

- Windows
- Python 3.12（仓库按 `.venv` 虚拟环境组织）
- Playwright 1.64+
- 本机已安装 Google Chrome 或 Microsoft Edge（二者任一即可）

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install playwright
```

> 不需要执行 `playwright install`，脚本直接使用本机浏览器。

## 运行

```powershell
# 打开图形界面（上货 + 资讯两个 Tab）
.\.venv\Scripts\python.exe xianyu_auto_publish.py

# 无窗口抓取一次资讯（供计划任务使用）
.\.venv\Scripts\python.exe xianyu_auto_publish.py --job news
.\.venv\Scripts\python.exe xianyu_auto_publish.py --job news --max-articles 10
```

## 上货 Tab 使用步骤

1. 点击 **「1. 启动浏览器并登录」**。首次会打开一个全新的自动化浏览器窗口（独立 profile），在窗口内扫码登录闲鱼即可；登录态会自动保存。
2. 选择 **商品首图**（默认 `1.jpg`），填写 **宝贝描述**（不超过 1500 字），填写 **价格**，原价可选。
3. 点击 **「2. 开始自动上货」**，在日志面板观察执行过程。
4. 核对发布页内容（分类、成色等由闲鱼自动识别），确认无误后手动点击页面上的 **【发布】**。
5. 点击 **「关闭浏览器」** 结束本次会话。

## 资讯抓取 Tab 使用步骤

1. 点击 **「1. 开始抓取」**：无窗口（headless）打开新浪体育，先收集首页与滚动列表的文章链接，再逐篇抓正文。
2. 单次上限默认 20 篇（可在 Tab 内改 1-100），正文之间默认间隔 1.5 秒，避免给站点造成压力。
3. 抓取结果按天写入 `data/news/YYYY-MM-DD.json`，同一天多次抓取会**追加并去重**（历史文件里出现过的链接不再抓取）。
4. 点 **「打开数据目录」** 可直接查看落盘文件。

### 每天定时抓取

- **GUI 定时**：勾选「每天定时抓取」，填 `HH:MM`（如 `08:30`），点「保存定时」。设置会写入 `config/news_sources.json` 的 `schedule` 字段。程序必须保持运行；程序启动时若已过当天定时时间且当天还没抓过，会立即补抓一次。
- **Windows 计划任务**（无需保持 GUI 运行）：

```powershell
schtasks /Create /TN "SinaSportsNews" /TR "\"C:\path\to\xianyu_auto_publish.py 所在目录\.venv\Scripts\pythonw.exe\" \"C:\path\to\xianyu_auto_publish.py\" --job news" /SC DAILY /ST 08:30
```

> 把命令里的两处路径替换成实际路径；用 `pythonw.exe` 可以避免每天弹出控制台窗口。

## 目录结构

```
.
├── xianyu_auto_publish.py     # 入口：GUI 编排 + --job news 无窗口任务
├── automation/                # 自动化层
│   ├── browser.py             # 本机 Chromium 探测、持久化上下文启动、元素定位工具
│   ├── worker.py              # 通用 Playwright 工作线程（一个实例一套浏览器上下文）
│   ├── tasks_publish.py       # 上货任务（写操作）
│   └── tasks_news.py          # 资讯抓取任务（只读）
├── ui/                        # 界面层
│   ├── log_panel.py           # 日志面板（[上货]/[资讯] 前缀 + 过滤）
│   ├── publish_tab.py         # 上货 Tab
│   └── news_tab.py            # 资讯 Tab（含定时）
├── config/news_sources.json   # 资讯来源、单次上限、间隔、定时设置
├── data/news/                 # 运行时生成：按天 JSON（勿提交）
├── 发布页元素定位.md           # 闲鱼发布页真实 DOM 与元素定位说明
├── 新浪体育元素定位.md         # 新浪体育列表/详情页元素定位说明
├── 1.jpg                      # 默认首图示例
├── README.md
├── TEST_REPORT.md
├── browser_profile/           # 运行时生成：上货浏览器目录（含登录态，勿提交）
└── news_profile/              # 运行时生成：资讯浏览器目录（勿提交）
```

## 资讯数据格式

```json
{
  "date": "2026-11-03",
  "fetched_at": "2026-11-03 23:57:03",
  "source": "sports.sina.com.cn",
  "count": 21,
  "added": 1,
  "articles": [
    {
      "title": "126期郭小舟大乐透预测奖号：跨度和值分析",
      "url": "https://sports.sina.com.cn/.../doc-xxxx.shtml",
      "time": "2026-11-03 23:53",
      "source": "新浪体育",
      "body": "正文（纯文本，段落以换行分隔，不含配图）",
      "fetched_at": "2026-11-03 23:57:03"
    }
  ]
}
```

## 元素定位说明

闲鱼发布页结构、字段清单和选择器写法见 [发布页元素定位.md](发布页元素定位.md)。要点：

- 页面是 JS 渲染（CSR），`Ctrl+U` 的源码里没有表单，必须取渲染后的 DOM。
- 带哈希后缀的 class（如 `upload-item--VvK_FTdU`）会随版本变化，定位一律使用 Ant Design 稳定类名与 `label[for]` 结构。
- 价格、原价、邮费三个输入框 `placeholder` 全是 `0.00` 且无对应 `id`，只能通过 `label[for]` → `ant-form-item` → `input` 定位。
- 新浪体育首页是服务端渲染，可直接取链接；滚动列表（`sports.sina.com.cn/roll/`）是 JS 渲染，需等待数秒再取行数据。

## 已知限制

- **登录必须手动**：脚本不处理账号密码或扫码流程。
- **发布必须手动**：为避免误发布，脚本只负责填表。
- 仅支持单张首图上传，多图上传未实现。
- 分类、成色等「属性规格」依赖闲鱼侧的自动识别，脚本不填写。
- 资讯**只取正文文本，不下载配图**；抓取站点结构若改版，选择器需要同步调整。
- 资讯按 URL 去重，只保留当天新出现的内容；历史抓取量与日俱增，可按需清理 `data/news/`。
- 未做验证码、风控、异地登录等异常处理；请控制使用频率。
- 浏览器回退到 Edge 时，窗口顶部可能出现「由自动测试软件控制」提示条，属正常现象。

## 免责声明

本项目仅用于个人学习与自动化技术研究。请遵守闲鱼用户协议与平台规则，抓取公开资讯时保持合理频率，因不当使用造成的风险由使用者自行承担。
