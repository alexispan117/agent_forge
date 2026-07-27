"""AgentForge — Agent 抽象基类"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseRuntime(ABC):
    """所有 Agent 的抽象基类。
    
    所有 Agent 必须继承此类并实现以下方法：
    - name:        Agent 的唯一标识名称
    - description: Agent 的功能描述
    - execute:     Agent 的核心执行逻辑
    
    可选实现：
    - init:        加载配置时执行初始化
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 的唯一名称（用于 CLI 调用，如 `run search`）"""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Agent 的功能描述（在 list 命令中展示）"""
        ...
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行 Agent 的核心逻辑。
        
        Args:
            **kwargs: 由 CLI 传入的参数
            
        Returns:
            执行结果（dict 或其他可序列化对象）
        """
        ...
    
    def init(self, config: dict) -> None:
        """初始化 Agent（可选重写）。
        
        在每次 run 之前调用，传入全局配置。
        适合在此处初始化 API 客户端、加载资源等。
        """
        pass
