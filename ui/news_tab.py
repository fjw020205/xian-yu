# -*- coding: utf-8 -*-
"""资讯抓取 Tab：手动抓取 + 每天定时抓取（定时只在程序运行期间生效）。"""

import os
import re
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from automation.tasks_news import DEFAULT_DATA_DIR, load_config, save_config

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class NewsTab(ttk.Frame):
    def __init__(self, master, worker):
        super().__init__(master, padding=(10, 8))
        self.worker = worker
        self._busy = False
        self._timer = None
        self._timer_gen = 0
        self._last_run_day = None
        self._timer_is_triggering = False

        self.max_var = tk.StringVar(value="20")
        self.status_var = tk.StringVar(value="尚未抓取")
        self.schedule_enabled = tk.BooleanVar(value=False)
        self.schedule_time = tk.StringVar(value="08:30")

        self._build()
        self._load_schedule()

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

        timer_row = ttk.Frame(self)
        timer_row.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            timer_row, text="每天定时抓取", variable=self.schedule_enabled,
            command=self._toggle_schedule,
        ).pack(side="left")
        ttk.Entry(timer_row, textvariable=self.schedule_time, width=8).pack(
            side="left", padx=6
        )
        ttk.Button(timer_row, text="保存定时", command=self._toggle_schedule).pack(
            side="left"
        )
        ttk.Label(
            timer_row, text="（HH:MM，程序需保持运行）", foreground="#666666"
        ).pack(side="left", padx=6)

        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 0))
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
            row=4, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

    # ---------- 抓取状态 ----------
    def set_busy(self, busy):
        if busy == self._busy:
            return
        self._busy = busy
        self.fetch_button.configure(state="disabled" if busy else "normal")
        self.status_var.set("正在抓取…" if busy else "抓取已结束，详情见日志")

    def _start_fetch(self, _event=None):
        raw = self.max_var.get().strip()
        try:
            limit = int(raw)
            if not 1 <= limit <= 100:
                raise ValueError
        except ValueError:
            if self._timer_is_triggering:
                self.worker.log("定时抓取的单次上限无效，已跳过")
            else:
                messagebox.showwarning("提示", "单次上限需要是 1-100 之间的整数")
            return
        if self.worker.busy:
            self.worker.log("已有抓取任务在执行，本次跳过")
            return
        self.worker.submit("fetch", {"max_articles": limit})

    def _stop_browser(self):
        self.worker.submit("stop")

    def _open_data_dir(self):
        if DEFAULT_DATA_DIR.is_dir():
            os.startfile(str(DEFAULT_DATA_DIR))
        else:
            messagebox.showinfo("提示", "还没有抓取数据，先点【开始抓取】")

    # ---------- 定时 ----------
    def _load_schedule(self):
        try:
            schedule = load_config().get("schedule", {})
        except (ValueError, OSError):
            schedule = {}
        self.schedule_enabled.set(bool(schedule.get("enabled", False)))
        if schedule.get("time"):
            self.schedule_time.set(schedule["time"])
        if self.schedule_enabled.get():
            self.worker.log(f"定时抓取已启用：每天 {self.schedule_time.get()}")
            self._start_timer()

    def _toggle_schedule(self):
        enabled = self.schedule_enabled.get()
        target = self.schedule_time.get().strip()
        if enabled and not TIME_PATTERN.match(target):
            messagebox.showwarning("提示", "定时时间格式应为 HH:MM，例如 08:30")
            self.schedule_enabled.set(False)
            return
        try:
            config = load_config()
            config["schedule"] = {"enabled": bool(enabled), "time": target}
            save_config(config)
        except (ValueError, OSError) as exc:
            messagebox.showwarning("提示", f"保存定时设置失败：{exc}")
            return

        if enabled:
            self.worker.log(f"定时抓取已启用：每天 {target}（程序运行期间生效）")
            self._start_timer()
        else:
            self.worker.log("定时抓取已关闭")
            self.stop_timer()

    def _start_timer(self):
        # 用代次号作废旧定时链，避免 after_cancel 造成销毁时重复删除 Tcl 命令
        self._timer_gen += 1
        generation = self._timer_gen
        self._timer = self.after(30000, lambda: self._tick_schedule(generation))

    def stop_timer(self):
        self._timer_gen += 1
        self._timer = None

    def _tick_schedule(self, generation=None):
        if generation is not None and generation != self._timer_gen:
            return
        self._timer = None
        if not self.schedule_enabled.get():
            return
        if not self._busy:
            now = datetime.now()
            if self._last_run_day != now.date():
                due = datetime.strptime(
                    f"{now.date()} {self.schedule_time.get().strip()}", "%Y-%m-%d %H:%M"
                )
                if now >= due:
                    self._last_run_day = now.date()
                    self._timer_is_triggering = True
                    try:
                        self.worker.log(f"定时触发（{self.schedule_time.get().strip()}），开始抓取")
                        self._start_fetch()
                    finally:
                        self._timer_is_triggering = False
        self._start_timer()
