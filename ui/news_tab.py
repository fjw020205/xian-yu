# -*- coding: utf-8 -*-
"""资讯抓取 Tab：只读抓取新浪体育资讯并落盘到 data/news。"""

import os
import tkinter as tk
from tkinter import messagebox, ttk

from automation.tasks_news import DEFAULT_DATA_DIR


class NewsTab(ttk.Frame):
    def __init__(self, master, worker):
        super().__init__(master, padding=(10, 8))
        self.worker = worker
        self._busy = False

        self.max_var = tk.StringVar(value="20")
        self.status_var = tk.StringVar(value="尚未抓取")

        self._build()

    def _build(self):
        ttk.Label(
            self,
            text="抓取范围：新浪体育首页 + 滚动新闻列表 ｜ 深度：标题 / 链接 / 时间 / 正文（不含配图）",
            foreground="#444444",
            wraplength=700,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        row = ttk.Frame(self)
        row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Label(row, text="单次上限：").pack(side="left")
        ttk.Entry(row, textvariable=self.max_var, width=6).pack(side="left")
        ttk.Label(row, text="篇").pack(side="left", padx=(2, 16))
        ttk.Label(row, text=f"数据目录：{DEFAULT_DATA_DIR}").pack(side="left")

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self.fetch_button = ttk.Button(
            buttons, text="1. 开始抓取", command=self._start_fetch
        )
        self.fetch_button.pack(side="left")
        ttk.Button(buttons, text="关闭浏览器", command=self._stop_browser).pack(
            side="left", padx=8
        )
        ttk.Button(buttons, text="打开数据目录", command=self._open_data_dir).pack(
            side="left"
        )

        ttk.Label(self, textvariable=self.status_var, foreground="#666666").grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

    def set_busy(self, busy):
        if busy == self._busy:
            return
        self._busy = busy
        self.fetch_button.configure(state="disabled" if busy else "normal")
        self.status_var.set("正在抓取…" if busy else "抓取已结束，详情见日志")

    def _start_fetch(self):
        raw = self.max_var.get().strip()
        try:
            limit = int(raw)
            if not 1 <= limit <= 100:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "单次上限需要是 1-100 之间的整数")
            return
        self.worker.submit("fetch", {"max_articles": limit})

    def _stop_browser(self):
        self.worker.submit("stop")

    def _open_data_dir(self):
        if DEFAULT_DATA_DIR.is_dir():
            os.startfile(str(DEFAULT_DATA_DIR))
        else:
            messagebox.showinfo("提示", "还没有抓取数据，先点【开始抓取】")
