# AgentForge 帮助文档

## 简介
AgentForge 是一个 AI Agent 工具箱，支持多种智能助手的加载和运行。
当前包含搜索助手（SearchAgent）和智能问答客服（RAGAgent）。

## SearchAgent 搜索助手
- 支持百度 AI 搜索和 DuckDuckGo 搜索
- 可自定义搜索结果数量和搜索时间范围
- 支持 AI 摘要功能，自动整理搜索结果为结构化摘要
- 搜索结果缓存 5 分钟，重复搜索更快

## RAGAgent 智能问答客服
- 基于本地文档回答问题
- 支持多轮对话，记忆上下文
- 使用 TF-IDF 关键词搜索匹配相关文档段落
- 接入大模型（DeepSeek）生成专业回答
- 支持对话历史重置

## 配置文件 config.yaml
- engine: 搜索引擎选择（baidu / duckduckgo）
- baidu_api_key: 百度千帆 AI 搜索 API Key
- llm.enabled: 是否启用 AI 摘要/回答
- llm.api_key: DeepSeek 或 OpenAI 的 API Key

## 使用方式
- CLI: python main.py run search "关键词"
- CLI: python main.py run chat "你的问题"
- Web: 启动后访问 http://localhost:8000
