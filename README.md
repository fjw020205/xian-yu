# 咸鱼自动上货助手

基于 **Tkinter + Playwright** 的半自动闲鱼（goofish）PC 端上货工具。

登录和最终发布由人工完成，脚本负责：打开首页 → 点击「发闲置」→ 进入发布页 → 上传首图 → 填写宝贝描述 / 价格 / 原价。

## 功能

| 能力 | 实现方式 |
| --- | --- |
| 复用本机浏览器 | Playwright `channel` 启动本机 Chromium 浏览器，**不下载** playwright 自带浏览器 |
| 优先 Chrome | 自动探测 Google Chrome；未安装时回退到本机 Microsoft Edge，并写入日志 |
| 登录态保持 | 使用独立用户目录 `browser_profile/`，登录一次后后续自动复用，且不干扰日常浏览器 |
| 点击「发闲置」 | `a[href*="/publish"]` / 文本「发闲置」多级定位；新标签页捕获失败时直接跳转发布页地址兜底 |
| 上传首图 | 直接向隐藏的 `input[name="file"]` 注入文件，失败时回退点击上传区域走文件选择器 |
| 填写描述 | `[contenteditable="true"]` 编辑器填入并校验内容，失败回退键盘输入 |
| 填写价格 / 原价 | 按 `label[for]` 定位到 `div.ant-form-item` 容器，再取容器内 `input` |
| 实时日志 | Tkinter 下方日志面板，秒级时间戳显示每一步结果 |

最终「发布」按钮**不由脚本点击**，需人工核对后手动提交。

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
.\.venv\Scripts\python.exe xianyu_auto_publish.py
```

## 使用步骤

1. 点击 **「1. 启动浏览器并登录」**。
   首次会打开一个全新的自动化浏览器窗口（独立 profile），在窗口内扫码登录闲鱼即可；登录态会自动保存。
2. 选择 **商品首图**（默认 `1.jpg`），填写 **宝贝描述**（不超过 1500 字），填写 **价格**，原价可选。
3. 点击 **「2. 开始自动上货」**，在日志面板观察执行过程。
4. 核对发布页内容（分类、成色等由闲鱼自动识别），确认无误后手动点击页面上的 **【发布】**。
5. 点击 **「关闭浏览器」** 结束本次会话。

## 目录结构

```
.
├── xianyu_auto_publish.py     # 主程序（Tkinter GUI + Playwright 自动化）
├── 发布页元素定位.md           # 发布页真实 DOM 与元素定位说明
├── 1.jpg                      # 默认首图示例
├── README.md
├── TEST_REPORT.md
└── browser_profile/           # 运行时生成：浏览器用户目录（含登录态，勿提交）
```

## 元素定位说明

页面结构、字段清单和选择器写法见 [发布页元素定位.md](发布页元素定位.md)。要点：

- 页面是 JS 渲染（CSR），`Ctrl+U` 的源码里没有表单，必须取渲染后的 DOM。
- 带哈希后缀的 class（如 `upload-item--VvK_FTdU`）会随版本变化，定位一律使用 Ant Design 稳定类名与 `label[for]` 结构。
- 价格、原价、邮费三个输入框 `placeholder` 全是 `0.00` 且无对应 `id`，只能通过 `label[for]` → `ant-form-item` → `input` 定位。

## 已知限制

- **登录必须手动**：脚本不处理账号密码或扫码流程。
- **发布必须手动**：为避免误发布，脚本只负责填表。
- 仅支持单张首图上传，多图上传未实现。
- 分类、成色等「属性规格」依赖闲鱼侧的自动识别，脚本不填写。
- 未做验证码、风控、异地登录等异常处理；请控制使用频率。
- 浏览器回退到 Edge 时，窗口顶部可能出现「由自动测试软件控制」提示条，属正常现象。

## 免责声明

本项目仅用于个人学习与自动化技术研究。请遵守闲鱼用户协议与平台规则，因不当使用造成的账号风险由使用者自行承担。
