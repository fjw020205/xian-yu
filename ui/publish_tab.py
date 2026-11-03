# -*- coding: utf-8 -*-
"""上货 Tab：表单 + 三个按钮，命令直接投给上货 worker。"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from automation.browser import BASE_DIR, DEFAULT_IMAGE


class PublishTab(ttk.Frame):
    def __init__(self, master, worker):
        super().__init__(master, padding=(10, 8))
        self.worker = worker

        self.image_var = tk.StringVar(
            value=str(DEFAULT_IMAGE) if DEFAULT_IMAGE.is_file() else ""
        )
        self.price_var = tk.StringVar()
        self.orig_price_var = tk.StringVar()

        self._build_form()
        self._build_buttons()

    def _build_form(self):
        ttk.Label(self, text="商品首图：").grid(row=0, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.image_var).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Button(self, text="浏览...", command=self._choose_image).grid(row=0, column=2)

        ttk.Label(self, text="宝贝描述：").grid(row=1, column=0, sticky="nw", pady=(10, 0))
        self.desc_text = tk.Text(self, height=5, wrap="word")
        self.desc_text.grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(10, 0)
        )

        price_row = ttk.Frame(self)
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
        self.columnconfigure(1, weight=1)

    def _build_buttons(self):
        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="1. 启动浏览器并登录", command=self._start_browser).pack(
            side="left"
        )
        ttk.Button(buttons, text="2. 开始自动上货", command=self._start_publish).pack(
            side="left", padx=8
        )
        ttk.Button(buttons, text="关闭浏览器", command=self._stop_browser).pack(side="left")

        ttk.Label(
            self,
            text="首次使用请先登录咸鱼账号；登录态保存在 browser_profile 目录，后续无需重复登录。",
            foreground="#666666",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _choose_image(self):
        path = filedialog.askopenfilename(
            title="选择商品首图",
            initialdir=str(BASE_DIR),
            filetypes=[("图片", "*.jpg *.jpeg *.png *.webp"), ("所有文件", "*.*")],
        )
        if path:
            self.image_var.set(path)

    def _start_browser(self):
        self.worker.log("正在启动浏览器...")
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
        self.worker.log("开始执行自动上货...")
        self.worker.submit("publish", data)

    def _stop_browser(self):
        self.worker.submit("stop")
