#!/usr/bin/env python3
"""🤖 AgentForge — AI Agent 工具箱（CLI 版）

用法:
    python main.py list              # 列出所有 Agent
    python main.py run <agent> ...   # 运行指定 Agent
    python main.py info <agent>      # 查看 Agent 详情

示例:
    python main.py run search "DeepSeek V4 最新特性"
    python main.py run search max_results=10 "Python 异步编程"
"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from core.config import load_config
from runtimes import discover_agents

console = Console()


# ── CLI 命令 ──


@click.group()
def cli():
    """🤖 AgentForge — AI Agent 工具箱"""
    pass


@cli.command()
def list():
    """📋 列出所有可用 Agent"""
    agents = discover_agents()

    if not agents:
        console.print("[yellow]暂无可用 Agent[/]")
        console.print("[dim]提示: 在 runtimes/ 目录下添加新的 Runtime 文件即可自动注册[/]")
        return

    table = Table(title="🤖 可用 Agent", box=box.ROUNDED)
    table.add_column("名称", style="cyan", width=15)
    table.add_column("描述", style="white")

    for name, agent in sorted(agents.items()):
        table.add_row(name, agent.description)

    console.print(table)
    console.print(f"\n[dim]共 {len(agents)} 个 Agent | 使用 [bold]run <名称>[/] 运行[/]")


@cli.command()
@click.argument("name", metavar="<agent_name>")
@click.argument("args", nargs=-1, metavar="[参数...]")
def run(name: str, args: tuple):
    """🚀 运行指定 Agent

    参数可以传无名参数（自动作为 query）或 key=value 形式。

    示例:
        python main.py run search "关键词"
        python main.py run search max_results=10 "关键词"
    """
    agents = discover_agents()
    config = load_config()

    if name not in agents:
        console.print(f"[red]❌ 未找到 Agent: {name}[/]")
        available = ", ".join(agents.keys())
        console.print(f"[dim]可用 Agent: {available}[/]")
        sys.exit(1)

    agent = agents[name]

    # 初始化（传入全局配置）
    agent.init(config)

    # 解析参数
    kwargs: dict = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            # 尝试转数字
            try:
                kwargs[key] = int(value)
            except ValueError:
                try:
                    kwargs[key] = float(value)
                except ValueError:
                    kwargs[key] = value
        else:
            # 首个无名参数作为 query
            kwargs["query"] = arg

    # 执行 Agent
    try:
        result = agent.execute(**kwargs)
        if isinstance(result, dict) and "error" in result:
            console.print(f"\n[red]❌ Agent 执行出错: {result['error']}[/]")
            sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Agent 执行异常: {e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("name", metavar="<agent_name>")
def info(name: str):
    """ℹ️ 查看 Agent 详情"""
    agents = discover_agents()

    if name not in agents:
        console.print(f"[red]❌ 未找到 Agent: {name}[/]")
        return

    agent = agents[name]
    console.print(Panel(
        f"[bold cyan]{agent.name}[/]\n\n{agent.description}",
        title="ℹ️ Agent 信息",
        border_style="cyan",
    ))


# ── 入口 ──

if __name__ == "__main__":
    cli()
