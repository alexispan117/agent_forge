"""AgentForge — 动态 Prompt 组装器

根据当前场景动态选择并拼接 Prompt 片段。
"""

from typing import Any


class PromptBuilder:
    """动态 Prompt 组装器

    根据会话状态、用户偏好、长期记忆等信息，
    动态选择 System Prompt、注入上下文、组装 Few-shot 示例。
    """

    def __init__(self):
        self._sections: list[dict] = []

    def add_system(self, text: str):
        """添加 System Prompt 段"""
        self._sections.append({"type": "system", "content": text})

    def add_rules(self, rules: list[str]):
        """添加规则列表"""
        text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))
        self._sections.append({"type": "rules", "content": f"## 规则\n{text}"})

    def add_context(self, label: str, content: str):
        """添加上下文段"""
        if content and content.strip():
            self._sections.append({"type": "context", "content": f"## {label}\n{content}"})

    def add_examples(self, examples: list[dict]):
        """添加 Few-shot 示例"""
        if not examples:
            return
        parts = ["## 示例"]
        for ex in examples:
            parts.append(f"用户: {ex.get('user', '')}")
            parts.append(f"助手: {ex.get('assistant', '')}")
        self._sections.append({"type": "examples", "content": "\n".join(parts)})

    def add_memory(self, long_term_memory: Any = None):
        """注入长期记忆"""
        if long_term_memory:
            blob = long_term_memory.context_blob()
            if blob and blob != "(无长期记忆)":
                self._sections.append({"type": "memory", "content": blob})

    def add_working_memory(self, notepad=None, todo=None):
        """注入工作记忆"""
        parts = []
        if notepad:
            summary = notepad.summary()
            if summary != "(无笔记)":
                parts.append(f"## 工作笔记\n{summary}")
        if todo:
            progress = todo.progress()
            if progress != "(无任务)":
                parts.append(f"## 任务进度\n{progress}")
        if parts:
            self._sections.append({"type": "working", "content": "\n\n".join(parts)})

    def build(self, user_query: str = "") -> list[dict]:
        """组装最终的 Messages

        Returns:
            [{"role": "system", "content": str}, {"role": "user", "content": str}]
        """
        # 系统 Prompt：合并所有 sections
        sys_parts = []
        for section in self._sections:
            if section["type"] == "system":
                sys_parts.append(section["content"])
            elif section["type"] in ("rules", "context", "examples", "memory", "working"):
                sys_parts.append(section["content"])

        system_text = "\n\n".join(sys_parts)
        messages = [{"role": "system", "content": system_text}]

        if user_query:
            messages.append({"role": "user", "content": user_query})

        return messages

    def clear(self):
        self._sections.clear()
