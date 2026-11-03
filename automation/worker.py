# -*- coding: utf-8 -*-
"""通用 Playwright 工作线程。

一个实例 = 一个 Playwright + 一个浏览器上下文 + 一个命令队列。
上货与资讯各建一个实例，彼此隔离；Tkinter 只负责往队列里投命令。

日志约定：写入 log_queue 的元素是 (标签, 消息) 二元组，
标签用于界面区分 [上货] / [资讯]。
"""

import queue
import threading

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from .browser import PUBLISH_PROFILE_DIR, active_page, launch_context


class AutomationWorker(threading.Thread):
    def __init__(
        self,
        log_queue,
        label,
        profile_dir=PUBLISH_PROFILE_DIR,
        headless=False,
        handlers=None,
    ):
        super().__init__(daemon=True)
        self.log_queue = log_queue
        self.label = label
        self.profile_dir = profile_dir
        self.headless = headless
        self.handlers = dict(handlers or {})  # 命令名 -> callable(payload)
        self.commands = queue.Queue()
        self.playwright = None
        self.context = None

    def log(self, message):
        self.log_queue.put((self.label, message))

    def submit(self, command, payload=None):
        self.commands.put((command, payload))

    def run(self):
        self.playwright = sync_playwright().start()
        try:
            while True:
                try:
                    command, payload = self.commands.get(timeout=0.5)
                except queue.Empty:
                    continue
                if command == "stop":
                    self.close_browser()
                    break
                handler = self.handlers.get(command)
                if handler is None:
                    self.log(f"未知命令：{command}")
                    continue
                try:
                    handler(payload)
                except PWTimeoutError as exc:
                    self.log(f"超时：{exc}")
                except PWError as exc:
                    self.log(f"浏览器操作失败：{exc}")
                except Exception as exc:  # 保证线程不因异常退出
                    self.log(f"异常：{exc}")
        finally:
            self.close_browser()
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

    # ---------- 浏览器 ----------
    def open_browser(self, url):
        """首次调用时启动浏览器，之后复用上下文并跳转。返回当前页面。"""
        if self.context:
            page = self.active_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return page
        self.context = launch_context(
            self.playwright, self.profile_dir, self.headless, self.log
        )
        page = self.active_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return page

    def active_page(self, host=None):
        return active_page(self.context, host)

    def close_browser(self):
        if self.context:
            try:
                self.context.close()
            except PWError:
                pass
            self.log("浏览器已关闭")
        self.context = None
