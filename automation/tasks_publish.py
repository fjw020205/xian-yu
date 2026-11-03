# -*- coding: utf-8 -*-
"""上货任务：写操作，需人工登录，最终【发布】由人工点击。

命令：
- start：启动浏览器（或复用已启动的）并打开咸鱼首页
- publish：首页 -> 点击【发闲置】-> 发布页 -> 上传首图 -> 填写描述/价格/原价
"""

import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeoutError

from .browser import HOME_URL, PUBLISH_URL, first_visible


class PublishTask:
    def __init__(self, worker):
        self.worker = worker

    @property
    def log(self):
        return self.worker.log

    def handlers(self):
        return {"start": self.start, "publish": self.publish}

    # ---------- 浏览器 ----------
    def start(self, _payload=None):
        existed = self.worker.context is not None
        self.worker.open_browser(HOME_URL)
        if existed:
            self.log("浏览器已在运行，已重新打开咸鱼首页")
        else:
            self.log("已打开咸鱼首页，请在浏览器中手动完成登录，然后点击【开始自动上货】")

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
    def publish(self, data):
        if not self.worker.context:
            self.log("请先点击【启动浏览器并登录】")
            return

        image = Path(data.get("image", ""))
        if not image.is_file():
            self.log(f"图片不存在：{image}")
            return

        page = self.worker.active_page("goofish.com")
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
            with self.worker.context.expect_page(timeout=8000) as page_info:
                entry.click()
            publish_page = page_info.value
            self.log("已在新的标签页打开发布页")
        except PWTimeoutError:
            self.log("未捕获到新标签页，检查已打开的页面地址...")
            page.wait_for_timeout(2000)
            for opened in self.worker.context.pages:
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
