# -*- coding: utf-8 -*-
"""咸鱼自动上货助手（Tkinter + Playwright）入口。

界面结构：
- 「上货」Tab：启动浏览器并登录 -> 点击【发闲置】-> 上传首图 -> 填写描述/价格/原价，
  最终【发布】由用户手动点击。
- 日志面板：区分 [上货] / [资讯] 前缀，可按来源过滤。

自动化逻辑在 automation/ 包内（browser / worker / tasks_publish），
界面组件在 ui/ 包内。使用本机已安装的 Chrome / Edge（channel 方式启动，不下载浏览器）。
"""

import argparse
import queue
import time
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

        self._closing = False
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
        if self._closing:
            return
        self._closing = True
        self.news_tab.stop_timer()
        self.publish_worker.submit("stop")
        self.news_worker.submit("stop")
        try:
            self.destroy()
        except tk.TclError:
            # 在 Tk 回调内销毁时，Tkinter 会重复删除自身命令，属收尾噪音
            pass
        self.quit()


def run_news_job(max_articles=None):
    """无窗口执行一次资讯抓取，供 Windows 计划任务调用。"""
    logs = queue.Queue()
    worker = AutomationWorker(
        logs, LABEL_NEWS, profile_dir=NEWS_PROFILE_DIR, headless=True
    )
    worker.handlers.update(NewsTask(worker).handlers())
    worker.start()
    worker.submit("fetch", {"max_articles": max_articles} if max_articles else {})

    started = False
    deadline = time.time() + 900
    while time.time() < deadline:
        try:
            label, message = logs.get(timeout=0.2)
            print(f"[{time.strftime('%H:%M:%S')}] [{label}] {message}", flush=True)
            continue
        except queue.Empty:
            pass
        if worker.busy:
            started = True
        elif started:
            break
    else:
        print("抓取超过 15 分钟仍未结束，已中止", flush=True)

    worker.submit("stop")
    worker.join(timeout=10)
    return 0


def main():
    parser = argparse.ArgumentParser(description="咸鱼自动上货 / 新浪体育资讯抓取")
    parser.add_argument(
        "--job", choices=("news",), help="无窗口执行一次资讯抓取（供 Windows 计划任务使用）"
    )
    parser.add_argument(
        "--max-articles", type=int, default=None, help="配合 --job news 指定单次抓取上限"
    )
    args = parser.parse_args()

    if args.job == "news":
        return run_news_job(args.max_articles)

    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    main()
