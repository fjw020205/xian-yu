# -*- coding: utf-8 -*-
"""咸鱼自动上货助手（Tkinter + Playwright）入口。

流程：
1. 点击【启动浏览器并登录】打开 goofish 首页，由用户手动完成登录（脚本不处理登录）。
2. 登录后点击【开始自动上货】：回到首页 -> 点击侧边栏【发闲置】-> 进入发布页 ->
   上传首图、填写宝贝描述、价格/原价。最终【发布】由用户手动点击。

说明：
- 自动化逻辑在 automation/ 包内：browser.py（浏览器探测与启动）、worker.py（工作线程）、
  tasks_publish.py（上货任务）。本文件只保留 Tkinter 界面与入口。
- 使用本机已安装的浏览器（优先 Google Chrome，未安装时回退本机 Microsoft Edge），
  使用 channel 方式启动，不执行 playwright install，不下载任何浏览器。
- 浏览器使用独立的用户数据目录 browser_profile/，登录态会保留，无需每次登录。
"""

import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from automation.browser import BASE_DIR, DEFAULT_IMAGE, PUBLISH_PROFILE_DIR
from automation.tasks_publish import PublishTask
from automation.worker import AutomationWorker

PUBLISH_LABEL = "上货"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("咸鱼自动上货助手")
        self.geometry("760x640")
        self.minsize(680, 560)

        self.log_queue = queue.Queue()
        self.worker = AutomationWorker(
            self.log_queue, PUBLISH_LABEL, profile_dir=PUBLISH_PROFILE_DIR
        )
        self.worker.handlers.update(PublishTask(self.worker).handlers())
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
        self._append_log(PUBLISH_LABEL, "正在启动浏览器...")
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
        self._append_log(PUBLISH_LABEL, "开始执行自动上货...")
        self.worker.submit("publish", data)

    def _stop_browser(self):
        self.worker.submit("stop")

    def _append_log(self, label, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] [{label}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _drain_logs(self):
        while True:
            try:
                label, message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(label, message)
        self.after(100, self._drain_logs)

    def _on_close(self):
        self.worker.submit("stop")
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
