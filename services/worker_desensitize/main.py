"""services/worker_desensitize/main.py — 脱敏 Worker（端口 8002）

通过 MCP/A2A 协议暴露脱敏能力：
- desensitize_text：五类敏感字段规则脱敏（不依赖 LLM 的确定性引擎）
- validate_desensitization：脱敏完整性校验
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SERVICE_TYPE", "desensitize")
os.environ.setdefault("LLM_MOCK_MODE", "true")

from core.with_fallback import with_fallback
from orchestration.agent_protocol import AgentCard, ToolSpec, build_protocol_router

# 内置脱敏规则（不依赖 LLM 的兜底方案）
MASK_RULES = {
    "id_card": (r"[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]",
                lambda m: m.group()[:6] + "********" + m.group()[-4:]),
    "phone": (r"1[3-9]\d{9}",
              lambda m: m.group()[:3] + "****" + m.group()[-4:]),
    "bank_card": (r"\d{16,19}",
                  lambda m: m.group()[:4] + "********" + m.group()[-4:]),
    "email": (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
              lambda m: m.group()[0] + "***@" + m.group().split("@")[1]),
    "ip": (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
           lambda m: ".".join(m.group().split(".")[:2]) + ".*.*"),
}


@with_fallback(service="desensitize", max_retries=1)
def desensitize_text(text: str, rules: list[str] | None = None) -> dict:
    """对文本执行脱敏。"""
    results = {}
    masked = text

    rule_keys = rules or list(MASK_RULES.keys())
    for key in rule_keys:
        if key in MASK_RULES:
            pattern, mask_fn = MASK_RULES[key]
            matches = re.findall(pattern, masked)
            count = len(matches)
            masked = re.sub(pattern, mask_fn, masked)
            if count > 0:
                results[key] = count

    return {
        "original_length": len(text),
        "masked_length": len(masked),
        "fields_masked": results,
        "total_masked": sum(results.values()),
        "masked_text": masked,
    }


@with_fallback(service="desensitize")
def validate_desensitization(text: str) -> dict:
    """验证脱敏是否完整。"""
    remaining = {}
    for key, (pattern, _) in MASK_RULES.items():
        matches = re.findall(pattern, text)
        if matches:
            remaining[key] = len(matches)
    return {
        "compliant": len(remaining) == 0,
        "remaining_fields": remaining,
    }


# ── A2A AgentCard ──
CARD = AgentCard(
    name="worker-desensitize",
    description="脱敏 Worker：身份证/手机号/银行卡/邮箱/IP 五类敏感字段脱敏与校验",
    endpoint=os.environ.get("WORKER_DESENSITIZE_URL", "http://localhost:8002"),
    capabilities=["desensitize", "validate", "pii_masking"],
    tools=[
        ToolSpec(
            name="desensitize_text",
            description="对文本执行五类敏感字段脱敏",
            input_schema={"type": "object",
                          "properties": {"text": {"type": "string"},
                                         "rules": {"type": "array", "items": {"type": "string"}}},
                          "required": ["text"]},
        ),
        ToolSpec(
            name="validate_desensitization",
            description="校验文本中是否仍有残留敏感字段",
            input_schema={"type": "object",
                          "properties": {"text": {"type": "string"}},
                          "required": ["text"]},
        ),
    ],
)

TOOLS = {"desensitize_text": desensitize_text, "validate_desensitization": validate_desensitization}


def create_app():
    from fastapi import FastAPI
    app = FastAPI(title="Worker-Desensitize")
    app.include_router(build_protocol_router(card=CARD, tools=TOOLS))

    @app.post("/desensitize")
    def api_desensitize(data: dict):
        return desensitize_text(data.get("text", ""), data.get("rules"))

    @app.post("/validate")
    def api_validate(data: dict):
        return validate_desensitization(data.get("text", ""))

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
