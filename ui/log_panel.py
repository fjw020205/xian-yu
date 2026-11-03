# -*- coding: utf-8 -*-
"""日志面板：显示带来源前缀的日志，支持按来源过滤。"""

import time
import tkinter as tk
from tkinter import scrolledtext, ttk

FILTER_ALL = "全部"
LABEL_PUBLISH = "上货"
LABEL_NEWS = "资讯"


class LogPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._records = []  # (来源, 整行文本)

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Label(bar, text="日志过滤：").pack(side="left")
        self.filter_var = tk.StringVar(value=FILTER_ALL)
        self._combo = ttk.Combobox(
            bar,
            textvariable=self.filter_var,
            values=(FILTER_ALL, LABEL_PUBLISH, LABEL_NEWS),
            state="readonly",
            width=8,
        )
        self._combo.pack(side="left")
        self._combo.bind("<<ComboboxSelected>>", self._on_filter)
        ttk.Button(bar, text="清空日志", command=self.clear).pack(side="right")

        self.box = scrolledtext.ScrolledText(self, height=16, state="disabled")
        self.box.pack(fill="both", expand=True)

    def append(self, label, message):
        line = f"[{time.strftime('%H:%M:%S')}] [{label}] {message}"
        self._records.append((label, line))
        if self._matches(label):
            self._write(line)

    def clear(self):
        self._records.clear()
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.configure(state="disabled")

    def _matches(self, label):
        current = self.filter_var.get()
        return current == FILTER_ALL or current == label

    def _on_filter(self, _event=None):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        for label, line in self._records:
            if self._matches(label):
                self.box.insert("end", line + "\n")
        self.box.see("end")
        self.box.configure(state="disabled")

    def _write(self, line):
        self.box.configure(state="normal")
        self.box.insert("end", line + "\n")
        self.box.see("end")
        self.box.configure(state="disabled")
