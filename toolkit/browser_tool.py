"""AgentForge — 浏览器自动化（Playwright）

让 Agent 可以控制浏览器执行操作。
参考第9层「前沿方向」：Computer Use + 浏览器自动化 + 视觉理解。
"""

import json
from pathlib import Path


class BrowserAgent:
    """浏览器自动化 Agent

    使用 Playwright 控制浏览器。
    需要手动安装: pip install playwright && playwright install chromium

    能力：
    - navigate: 访问网页
    - screenshot: 截图（视觉理解）
    - click: 点击元素
    - type: 输入文字
    - extract: 提取文本
    """

    def __init__(self, headless: bool = True):
        self._browser = None
        self._page = None
        self._headless = headless
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def _ensure(self):
        if self._ready:
            return
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self._headless)
            self._page = self._browser.new_page(viewport={"width": 1280, "height": 720})
            self._ready = True
        except ImportError:
            raise RuntimeError("需要安装 playwright: pip install playwright && playwright install chromium")

    def navigate(self, url: str) -> dict:
        """访问网页"""
        self._ensure()
        self._page.goto(url, wait_until="networkidle")
        return {"url": self._page.url, "title": self._page.title()}

    def screenshot(self, path: str | None = None) -> str:
        """截图（视觉理解）"""
        self._ensure()
        if path is None:
            path = str(Path.home() / ".cache" / "agentforge" / "screenshots" / "latest.png")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=path, full_page=True)
        return path

    def click(self, selector: str) -> dict:
        """点击元素"""
        self._ensure()
        try:
            self._page.click(selector, timeout=5000)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def type_text(self, selector: str, text: str) -> dict:
        """输入文字"""
        self._ensure()
        try:
            self._page.fill(selector, text)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def extract_text(self) -> str:
        """提取页面文本"""
        self._ensure()
        return self._page.inner_text("body")[:5000]

    def extract_html(self) -> str:
        """提取页面 HTML"""
        self._ensure()
        return self._page.content()[:5000]

    def execute_js(self, script: str) -> dict:
        """执行 JavaScript"""
        self._ensure()
        try:
            result = self._page.evaluate(script)
            return {"success": True, "result": str(result)[:1000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close(self):
        """关闭浏览器"""
        if self._page:
            self._page.close()
        if self._browser:
            self._browser.close()
        if hasattr(self, "_playwright"):
            self._playwright.stop()
        self._ready = False
