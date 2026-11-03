# -*- coding: utf-8 -*-
"""咸鱼自动上货助手（Tkinter + Playwright）入口。

界面结构：
- 「上货」Tab：启动浏览器并登录 -> 点击【发闲置】-> 上传首图 -> 填写描述/价格/原价，
  最终【发布】由用户手动点击。
- 日志面板：区分 [上货] / [资讯] 前缀，可按来源过滤。

自动化逻辑在 automation/ 包内（browser / worker / tasks_publish），
界面组件在 ui/ 包内。使用本机已安装的 Chrome / Edge（channel 方式启动，不下载浏览器）。
"""

import queue
import tkinter as tk
from tkinter import ttk

from automation.browser import NEWS_PROFILE_DIR, PUBLISH_PROFILE_DIR
from automation.tasks_news import NewsTask
from automation.tasks_publish import PublishTask
from automation.worker import AutomationWorker
from ui.log_panel import LABEL_NEWS, LABEL_PUBLISH, LogPanel
from ui.news_tab import NewsTab
from ui.publish_tab import PublishTab


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("咸鱼自动上货 / 新浪体育资讯")
        self.geometry("800x720")
        self.minsize(720, 620)

        self.log_queue = queue.Queue()

        self.publish_worker = AutomationWorker(
            self.log_queue, LABEL_PUBLISH, profile_dir=PUBLISH_PROFILE_DIR
        )
        self.publish_worker.handlers.update(PublishTask(self.publish_worker).handlers())
        self.publish_worker.start()

        self.news_worker = AutomationWorker(
            self.log_queue, LABEL_NEWS, profile_dir=NEWS_PROFILE_DIR, headless=True
        )
        self.news_worker.handlers.update(NewsTask(self.news_worker).handlers())
        self.news_worker.start()

        self.notebook = ttk.Notebook(self)
        self.publish_tab = PublishTab(self.notebook, self.publish_worker)
        self.news_tab = NewsTab(self.notebook, self.news_worker)
        self.notebook.add(self.publish_tab, text=" 上货 ")
        self.notebook.add(self.news_tab, text=" 资讯抓取 ")
        self.notebook.pack(fill="x", padx=10, pady=(10, 0))

        self.log_panel = LogPanel(self)
        self.log_panel.pack(fill="both", expand=True, padx=10, pady=(8, 10))

        self.after(100, self._drain_logs)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _drain_logs(self):
        while True:
            try:
                label, message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_panel.append(label, message)
        self.news_tab.set_busy(self.news_worker.busy)
        self.after(100, self._drain_logs)

    def _on_close(self):
        self.publish_worker.submit("stop")
        self.news_worker.submit("stop")
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
