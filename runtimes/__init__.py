"""AgentForge — Agent 自动发现模块"""

import importlib
import pkgutil
from .base_runtime import BaseRuntime

__all__ = ["BaseRuntime", "discover_agents"]


def discover_agents() -> dict[str, BaseRuntime]:
    """自动发现 agents 包下所有 Agent 类。
    
    扫描 agents/ 目录下每个 .py 文件（除 base 和私有模块），
    找出所有 BaseRuntime 的非抽象子类并实例化。
    
    Returns:
        {agent_name: agent_instance, ...}
    """
    agents: dict[str, BaseRuntime] = {}
    
    for importer, modname, ispkg in pkgutil.iter_modules(__path__):
        # 跳过基类和私有模块
        if modname in ("base",) or modname.startswith("_"):
            continue
        
        # 动态导入模块
        module = importlib.import_module(f".{modname}", __package__)
        
        # 扫描模块中所有 BaseRuntime 子类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseRuntime)
                and attr is not BaseRuntime
                and not getattr(attr, "__isabstractmethod__", False)
            ):
                instance = attr()
                agents[instance.name] = instance
    
    return agents
