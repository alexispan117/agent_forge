"""AgentForge — 模板渲染（共享模块）

避免 web/app.py 和 web/auth.py 之间的循环导入。
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), auto_reload=True)


def render(name: str, **kwargs) -> str:
    return _env.get_template(name).render(**kwargs)
