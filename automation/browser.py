# -*- coding: utf-8 -*-
"""浏览器公共设施：本机 Chromium 探测、持久化上下文启动、可见元素定位。

约定：
- 使用本机已安装的浏览器（优先 Google Chrome，未安装时回退本机 Microsoft Edge），
  使用 channel 方式启动，不执行 playwright install，不下载任何浏览器。
- 每个任务使用独立用户数据目录，互不干扰，登录态可保留。
"""

import winreg
from pathlib import Path

from playwright.sync_api import Error as PWError

BASE_DIR = Path(__file__).resolve().parent.parent

# 上货：独立 profile，保留咸鱼登录态
PUBLISH_PROFILE_DIR = BASE_DIR / "browser_profile"
# 资讯：只读抓取，单独 profile，避免与上货的登录态混杂
NEWS_PROFILE_DIR = BASE_DIR / "news_profile"

HOME_URL = "https://www.goofish.com/"
PUBLISH_URL = "https://www.goofish.com/publish"
DEFAULT_IMAGE = BASE_DIR / "1.jpg"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
]
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _find_exe(paths, registry_root, registry_key):
    for path in paths:
        if Path(path).is_file():
            return path
    try:
        with winreg.OpenKey(registry_root, registry_key) as key:
            path = winreg.QueryValueEx(key, None)[0].strip('"')
            if Path(path).is_file():
                return path
    except OSError:
        pass
    return None


def detect_browser():
    """返回 (channel, 说明)。优先本机 Google Chrome，其次本机 Edge。"""
    chrome = _find_exe(
        CHROME_PATHS,
        winreg.HKEY_CURRENT_USER,
        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
    ) or _find_exe(
        CHROME_PATHS,
        winreg.HKEY_LOCAL_MACHINE,
        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
    )
    if chrome:
        return "chrome", f"使用本机 Google Chrome：{chrome}"
    edge = _find_exe(
        EDGE_PATHS,
        winreg.HKEY_LOCAL_MACHINE,
        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    ) or _find_exe(
        EDGE_PATHS,
        winreg.HKEY_CURRENT_USER,
        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    )
    if edge:
        return "msedge", f"未检测到 Google Chrome，改用本机 Microsoft Edge：{edge}"
    raise RuntimeError("未找到可用的本机 Chromium 浏览器（Chrome / Edge 均缺失）")


def launch_context(playwright, profile_dir, headless, log):
    """启动（或复用目录的）持久化浏览器上下文。

    log: 单参数回调，用于输出“使用哪个浏览器”的信息。
    """
    channel, info = detect_browser()
    log(info)
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    args = ["--disable-blink-features=AutomationControlled"]
    kwargs = {
        "user_data_dir": str(profile_dir),
        "channel": channel,
        "headless": headless,
        "args": args,
    }
    if headless:
        kwargs["viewport"] = {"width": 1440, "height": 900}
    else:
        kwargs["no_viewport"] = True
        args.append("--start-maximized")
    return playwright.chromium.launch_persistent_context(**kwargs)


def active_page(context, host=None):
    """取上下文中的活动页面：优先命中 host 的页面，否则取第一个页面。"""
    if context is None:
        return None
    pages = context.pages
    if host:
        for page in pages:
            if host in page.url:
                return page
    if pages:
        return pages[0]
    return context.new_page()


def first_visible(locator):
    """返回第一个可见元素，全部不可见时返回 None。"""
    try:
        count = locator.count()
    except PWError:
        return None
    for index in range(count):
        item = locator.nth(index)
        try:
            if item.is_visible():
                return item
        except PWError:
            continue
    return None
