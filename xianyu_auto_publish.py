# -*- coding: utf-8 -*-
"""咸鱼自动上货助手（Tkinter + Playwright）

流程：
1. 点击【启动浏览器并登录】打开 goofish 首页，由用户手动完成登录（脚本不处理登录）。
2. 登录后点击【开始自动上货】：回到首页 -> 点击侧边栏【发闲置】-> 进入发布页 ->
   上传首图、填写宝贝描述、价格/原价。最终【发布】由用户手动点击。

说明：
- 使用本机已安装的浏览器（优先 Google Chrome，未安装时回退本机 Microsoft Edge），
  使用 channel 方式启动，不执行 playwright install，不下载任何浏览器。
- 浏览器使用独立的用户数据目录 browser_profile/，登录态会保留，无需每次登录。
"""

import queue
import re
import threading
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "browser_profile"
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
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
    ) or _find_exe(
        CHROME_PATHS,
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
    )
    if chrome:
        return "chrome", f"使用本机 Google Chrome：{chrome}"
    edge = _find_exe(
        EDGE_PATHS,
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    ) or _find_exe(
        EDGE_PATHS,
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    )
    if edge:
        return "msedge", f"未检测到 Google Chrome，改用本机 Microsoft Edge：{edge}"
    raise RuntimeError("未找到可用的本机 Chromium 浏览器（Chrome / Edge 均缺失）")


def first_visible(locator):
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


class AutomationWorker(threading.Thread):
    """单线程持有 Playwright，Tkinter 通过命令队列驱动。"""

    def __init__(self, log_queue):
        super().__init__(daemon=True)
        self.log_queue = log_queue
        self.commands = queue.Queue()
        self.playwright = None
        self.context = None
        self.channel = None

    def log(self, message):
        self.log_queue.put(message)

    def submit(self, command, payload=None):
        self.commands.put((command, payload))

    def run(self):
        self.playwright = sync_playwright().start()
        while True:
            try:
                command, payload = self.commands.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if command == "start":
                    self._start_browser()
                elif command == "publish":
                    self._publish(payload)
                elif command == "stop":
                    self._close_browser()
                    break
            except PWTimeoutError as exc:
                self.log(f"超时：{exc}")
            except PWError as exc:
                self.log(f"浏览器操作失败：{exc}")
            except Exception as exc:  # 保证线程不因异常退出
                self.log(f"异常：{exc}")

    # ---------- 浏览器 ----------
    def _start_browser(self):
        if self.context:
            page = self._active_page()
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
            self.log("浏览器已在运行，已重新打开咸鱼首页")
            return

        self.channel, info = detect_browser()
        self.log(info)
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel=self.channel,
            headless=False,
            no_viewport=True,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        page = self._active_page()
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        self.log("已打开咸鱼首页，请在浏览器中手动完成登录，然后点击【开始自动上货】")

    def _close_browser(self):
        if self.context:
            try:
                self.context.close()
            except PWError:
                pass
            self.log("浏览器已关闭")
        self.context = None

    def _active_page(self):
        for page in self.context.pages:
            if "goofish.com" in page.url:
                return page
        if self.context.pages:
            return self.context.pages[0]
        return self.context.new_page()

    def _ensure_logged_in(self, page):
        """登录态判断：首页侧边栏出现【发闲置】即视为已登录。"""
        for base in (
            page.locator('a[href*="/publish"]'),
            page.get_by_text("发闲置", exact=True),
            page.locator('a:has-text("发闲置")'),
        ):
            if first_visible(base) is not None:
                return True
        return False

    def _find_publish_entry(self, page, timeout=20.0):
        deadline = time.time() + timeout
        bases = (
            page.locator('a[href*="/publish"]'),
            page.locator('a:has-text("发闲置")'),
            page.get_by_text("发闲置", exact=True),
            page.locator('a[class*="sidebar-item-wrap"]:has-text("发闲置")'),
        )
        while time.time() < deadline:
            for base in bases:
                element = first_visible(base)
                if element is not None:
                    return element
            page.wait_for_timeout(500)
        return None

    # ---------- 上货 ----------
    def _publish(self, data):
        if not self.context:
            self.log("请先点击【启动浏览器并登录】")
            return

        image = Path(data.get("image", ""))
        if not image.is_file():
            self.log(f"图片不存在：{image}")
            return

        page = self._active_page()
        self.log("正在打开咸鱼首页...")
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        if not self._ensure_logged_in(page):
            self.log("未检测到【发闲置】入口，请先在浏览器中完成登录，再重试")
            return

        self.log("已检测到登录状态，正在定位【发闲置】按钮...")
        entry = self._find_publish_entry(page)
        if entry is None:
            self.log("未找到【发闲置】按钮，页面结构可能已变化，请检查浏览器")
            return

        self.log("点击【发闲置】，等待发布页打开...")
        publish_page = None
        try:
            with self.context.expect_page(timeout=8000) as page_info:
                entry.click()
            publish_page = page_info.value
            self.log("已在新的标签页打开发布页")
        except PWTimeoutError:
            self.log("未捕获到新标签页，检查已打开的页面地址...")
            page.wait_for_timeout(2000)
            for opened in self.context.pages:
                if "/publish" in opened.url:
                    publish_page = opened
                    break
            if publish_page is None and "/publish" in page.url:
                publish_page = page

        if publish_page is None:
            self.log("页面未自动跳转，改为直接打开发布页地址")
            publish_page = page
            publish_page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
        else:
            self.log(f"发布页地址：{publish_page.url}")

        publish_page.wait_for_load_state("domcontentloaded", timeout=30000)
        try:
            publish_page.wait_for_url(re.compile(r"/publish"), timeout=30000)
        except PWTimeoutError:
            self.log(f"发布页地址校验失败，当前停留在：{publish_page.url}")

        self.log("进入发布页，开始上传首图...")
        self._upload_first_image(publish_page, image)
        self.log("开始填写宝贝描述与价格...")
        self._fill_form(publish_page, data)
        self.log("信息填写完成，请核对页面后点击【发布】按钮")

    def _find_file_input(self, page, timeout=20.0):
        deadline = time.time() + timeout
        selectors = (
            'input[name="file"][type="file"]',
            'input[type="file"][accept*="image"]',
            'input[type="file"]',
        )
        while time.time() < deadline:
            for selector in selectors:
                locator = page.locator(selector)
                if locator.count() > 0:
                    return locator.first
            page.wait_for_timeout(300)
        return None

    def _upload_first_image(self, page, image):
        file_input = self._find_file_input(page)

        if file_input is not None:
            file_input.set_input_files(str(image))
            self.log(f"已通过文件输入框上传首图：{image.name}")
            self._confirm_upload(page)
            return

        trigger = None
        for selector in (
            page.locator('[class*="upload-content"]'),
            page.locator('[class*="upload-item"]'),
            page.locator(".ant-upload-select"),
            page.get_by_text(re.compile(r"添加首图|添加图片|上传图片")),
        ):
            trigger = first_visible(selector)
            if trigger is not None:
                break
        if trigger is None:
            raise RuntimeError("未找到图片上传控件，无法上传首图")
        self.log("未找到隐藏的文件输入框，尝试点击上传区域唤起文件选择器...")
        try:
            with page.expect_file_chooser(timeout=15000) as chooser_info:
                trigger.click()
            chooser_info.value.set_files(str(image))
            self.log(f"已通过文件选择器上传首图：{image.name}")
            self._confirm_upload(page)
        except PWTimeoutError:
            raise RuntimeError("点击上传区域后未弹出文件选择器")

    def _confirm_upload(self, page):
        """软校验：等待宝贝图片列表出现预览图，超时只提示不改流程。"""
        self.log("等待图片上传/预览...")
        try:
            page.wait_for_function(
                """() => Array.from(document.querySelectorAll('[class*="imgList"]'))
                    .some(list => list.querySelectorAll('img').length > 0)""",
                timeout=20000,
            )
            self.log("已检测到首图预览")
        except PWTimeoutError:
            self.log("暂未检测到图片预览，请人工确认首图是否已显示在发布页")

    # ---------- 表单 ----------
    def _field_item(self, page, field_id):
        """按 label 的 for 属性找到对应的 ant-form-item 容器。"""
        xpath = (
            'xpath=//label[@for="%s"]/ancestor::div['
            'contains(concat(" ", normalize-space(@class), " "), " ant-form-item ")][1]' % field_id
        )
        return page.locator(xpath)

    def _fill_price(self, page, field_id, value, label):
        item = self._field_item(page, field_id)
        if item.count() == 0:
            self.log(f"未找到【{label}】输入框，已跳过")
            return
        box = item.locator("input").first
        box.scroll_into_view_if_needed()
        box.click()
        box.fill(str(value))
        page.keyboard.press("Tab")
        page.wait_for_timeout(300)
        self.log(f"已填写{label}：{box.input_value()}")

    def _fill_description(self, page, text):
        item = self._field_item(page, "itemTextDTO_desc")
        editor = (
            item.locator('[contenteditable="true"]').first
            if item.count() > 0
            else page.locator('[contenteditable="true"]').first
        )
        if editor.count() == 0:
            self.log("未找到【宝贝描述】编辑器，已跳过")
            return
        editor.scroll_into_view_if_needed()
        editor.click()
        editor.fill(text)
        page.wait_for_timeout(400)

        if editor.inner_text().strip() != text.strip():
            self.log("描述写入后内容不一致，改用键盘输入重试")
            editor.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.insert_text(text)
            page.wait_for_timeout(400)
        self.log(f"已填写宝贝描述（{len(text)} 字）")

    def _fill_form(self, page, data):
        page.wait_for_timeout(1000)
        desc = (data.get("desc") or "").strip()
        price = (data.get("price") or "").strip()
        orig_price = (data.get("orig_price") or "").strip()

        if desc:
            self._fill_description(page, desc)
        if price:
            self._fill_price(page, "itemPriceDTO_priceInCent", price, "价格")
        if orig_price:
            self._fill_price(page, "itemPriceDTO_origPriceInCent", orig_price, "原价")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("咸鱼自动上货助手")
        self.geometry("760x640")
        self.minsize(680, 560)

        self.log_queue = queue.Queue()
        self.worker = AutomationWorker(self.log_queue)
        self.worker.start()

        self.image_var = tk.StringVar(
            value=str(DEFAULT_IMAGE) if DEFAULT_IMAGE.is_file() else ""
        )
        self.price_var = tk.StringVar()
        self.orig_price_var = tk.StringVar()

        self._build_ui()
        self.after(100, self._drain_logs)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        padding = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self)
        frame.pack(fill="x", **padding)

        ttk.Label(frame, text="商品首图：").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.image_var).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(frame, text="浏览...", command=self._choose_image).grid(
            row=0, column=2
        )

        ttk.Label(frame, text="宝贝描述：").grid(
            row=1, column=0, sticky="nw", pady=(10, 0)
        )
        self.desc_text = tk.Text(frame, height=5, wrap="word")
        self.desc_text.grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(10, 0)
        )

        price_row = ttk.Frame(frame)
        price_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Label(price_row, text="价格(元)：").pack(side="left")
        ttk.Entry(price_row, textvariable=self.price_var, width=12).pack(
            side="left", padx=(0, 20)
        )
        ttk.Label(price_row, text="原价(元，可选)：").pack(side="left")
        ttk.Entry(price_row, textvariable=self.orig_price_var, width=12).pack(
            side="left", padx=(0, 20)
        )
        ttk.Label(price_row, text="描述上限 1500 字", foreground="#666666").pack(
            side="left"
        )
        frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **padding)
        ttk.Button(
            buttons, text="1. 启动浏览器并登录", command=self._start_browser
        ).pack(side="left")
        ttk.Button(
            buttons, text="2. 开始自动上货", command=self._start_publish
        ).pack(side="left", padx=8)
        ttk.Button(buttons, text="关闭浏览器", command=self._stop_browser).pack(
            side="left"
        )

        tip = ttk.Label(
            self,
            text="首次使用请先登录咸鱼账号；登录态会保存在 browser_profile 目录，后续无需重复登录。",
            foreground="#666666",
        )
        tip.pack(fill="x", padx=10)

        self.log_box = scrolledtext.ScrolledText(self, height=18, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(6, 10))

    def _choose_image(self):
        path = filedialog.askopenfilename(
            title="选择商品首图",
            initialdir=str(BASE_DIR),
            filetypes=[("图片", "*.jpg *.jpeg *.png *.webp"), ("所有文件", "*.*")],
        )
        if path:
            self.image_var.set(path)

    def _start_browser(self):
        self._append_log("正在启动浏览器...")
        self.worker.submit("start")

    def _start_publish(self):
        image = self.image_var.get().strip()
        if not image or not Path(image).is_file():
            messagebox.showwarning("提示", "请先选择有效的首图文件")
            return

        desc = self.desc_text.get("1.0", "end").strip()
        if not desc:
            messagebox.showwarning("提示", "请填写宝贝描述")
            return
        if len(desc) > 1500:
            messagebox.showwarning("提示", "宝贝描述不能超过 1500 字")
            return

        price = self.price_var.get().strip()
        try:
            if float(price) <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "请填写正确的价格（大于 0 的数字）")
            return

        orig_price = self.orig_price_var.get().strip()
        if orig_price:
            try:
                if float(orig_price) <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("提示", "原价需要是大于 0 的数字，或留空")
                return

        data = {
            "image": image,
            "desc": desc,
            "price": price,
            "orig_price": orig_price,
        }
        self._append_log("开始执行自动上货...")
        self.worker.submit("publish", data)

    def _stop_browser(self):
        self.worker.submit("stop")

    def _append_log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _drain_logs(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)
        self.after(100, self._drain_logs)

    def _on_close(self):
        self.worker.submit("stop")
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
