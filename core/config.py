"""AgentForge — 统一配置加载

单一事实来源：config.yaml + 环境变量。
- ${VAR} 占位符在加载时展开（未设置时展开为空字符串，绝不把真实密钥写进仓库）
- 自动加载项目根目录 .env（若存在）
- interfaces/app.py 与 main.py 均委托此处，避免两套展开逻辑漂移
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _load_dotenv() -> None:
    """轻量 .env 加载（不覆盖已存在的环境变量）。"""
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _expand(value):
    """递归展开字符串中的 ${ENV_VAR}。"""
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _audit_key_safety(raw: dict) -> None:
    """启动自检：config.yaml 中若存在未占位符化的真实密钥，打印警告。

    防止「把密钥直接写进 yaml」的误操作——占位符 ${VAR} 是唯一允许的形式。
    """
    import warnings

    _REAL_KEY = re.compile(
        r"(sk-[A-Za-z0-9]{16,}|bce-v3/[A-Za-z0-9]{16,}|[A-Za-z0-9]{32,})"
    )

    def walk(node, path: str):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            if _REAL_KEY.search(node):
                warnings.warn(
                    f"⚠️ 安全警告: config.yaml 的 '{path}' 疑似包含真实密钥！"
                    "请改用环境变量占位符 ${VAR}（如 ${LLM_API_KEY}），"
                    "真实密钥只放在 .env（已被 .gitignore 排除）。",
                    stacklevel=2,
                )

    walk(raw, "")


def load_config() -> dict:
    """加载全局配置（环境变量优先，密钥不落库）。"""
    _load_dotenv()
    if not CONFIG_PATH.exists():
        return {"llm": {"enabled": False}}
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    _audit_key_safety(raw)
    return _expand(raw)
