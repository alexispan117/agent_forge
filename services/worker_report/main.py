"""services/worker_report/main.py — 报告生成 Worker（端口 8003）

通过 MCP/A2A 协议暴露报告能力：
- generate_report：根据审计发现生成结案报告
- score_clear：CLEAR 五维评分计算
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SERVICE_TYPE", "report")
os.environ.setdefault("LLM_MOCK_MODE", "true")

from core.llm_factory import get_llm
from core.with_fallback import with_fallback
from orchestration.assessors.clear_scorer import CLEARScorer
from orchestration.agent_protocol import AgentCard, ToolSpec, build_protocol_router

llm = get_llm()
metrics = CLEARScorer("clear")


@with_fallback(service="report", max_retries=2)
def generate_report(findings: list, evaluation: dict | None = None) -> dict:
    """根据分析结果生成审计报告。"""
    findings_text = json.dumps(findings, ensure_ascii=False, indent=2)
    prompt = f"根据以下审计发现生成结案报告：\n{findings_text[:3000]}"

    content = llm.chat([{"role": "user", "content": prompt}])

    # 整合 CLEAR 评估
    if evaluation:
        content += f"\n\n### CLEAR 评估\n{evaluation}"

    metrics.record(success=True, latency_s=0.1, query="report_generation")

    return {
        "report": content,
        "findings_count": len(findings),
        "generated_at": time.time(),
    }


@with_fallback(service="report")
def score_clear(metrics_data: dict) -> dict:
    """计算 CLEAR 五维评分。"""
    # 成本 Cost: API 调用次数 × 单价
    cost = 100 - min(metrics_data.get("api_calls", 0) * 5, 80)
    # 延迟 Latency: 平均响应时间
    latency = 100 - min(metrics_data.get("avg_latency_s", 0) * 10, 80)
    # 效能 Efficacy: 任务完成率
    efficacy = metrics_data.get("success_rate", 0.85) * 100
    # 保证 Assurance: 审批通过率
    assurance = metrics_data.get("approval_rate", 0.9) * 100
    # 可靠性 Reliability: 无故障运行
    reliability = 100 - metrics_data.get("failure_count", 0) * 5

    return {
        "cost": min(cost, 100),
        "latency": min(latency, 100),
        "efficacy": min(efficacy, 100),
        "assurance": min(assurance, 100),
        "reliability": max(reliability, 50),
    }


# ── A2A AgentCard ──
CARD = AgentCard(
    name="worker-report",
    description="报告 Worker：审计结案报告生成、CLEAR 五维评估",
    endpoint=os.environ.get("WORKER_REPORT_URL", "http://localhost:8003"),
    capabilities=["report_generation", "clear_scoring"],
    tools=[
        ToolSpec(
            name="generate_report",
            description="根据审计发现生成结案报告",
            input_schema={"type": "object",
                          "properties": {"findings": {"type": "array"},
                                         "evaluation": {"type": "object"}},
                          "required": ["findings"]},
        ),
        ToolSpec(
            name="score_clear",
            description="计算 CLEAR 五维评分",
            input_schema={"type": "object",
                          "properties": {"metrics_data": {"type": "object"}},
                          "required": ["metrics_data"]},
        ),
    ],
)

TOOLS = {"generate_report": generate_report, "score_clear": score_clear}


def create_app():
    from fastapi import FastAPI
    app = FastAPI(title="Worker-Report")
    app.include_router(build_protocol_router(card=CARD, tools=TOOLS))

    @app.post("/generate")
    def api_generate(data: dict):
        return generate_report(data.get("findings", []), data.get("evaluation"))

    @app.post("/clear-score")
    def api_clear(data: dict):
        return score_clear(data.get("metrics", {}))

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8003))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
