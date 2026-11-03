# -*- coding: utf-8 -*-
"""自动化层。

- browser.py：本机 Chromium 探测、持久化上下文启动、可见元素定位等公共设施
- worker.py：通用 Playwright 工作线程（一个线程 = 一个 Playwright + 一个浏览器上下文）
- tasks_publish.py：上货任务（写操作，需登录）
- tasks_news.py：资讯抓取任务（只读）
"""
