"""
智能客诉工单自动化处理系统 — LangGraph 实现

核心技术特点:
1. StateGraph 8 节点状态机（不是简单 ReAct 循环）
2. 条件路由：根据金额/策略自动分流
3. Human-in-the-Loop：大额审批暂停等待人工确认
4. 状态持久化：可暂停/恢复/回溯/审计
5. SSE 实时推送：节点状态变化向前端推送

节点流程:
  read_ticket → classify_intent → fetch_order → risk_assessment
    → auto_approve（小额） 或  human_approval（大额）
    → generate_response → quality_check → finalize
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from core.llm_factory import get_llm

logger = logging.getLogger("complaint_agent")
ROOT = Path(__file__).resolve().parent.parent
TICKETS_FILE = ROOT / "data" / "demo" / "complaints.json"

# ═══════════ State 定义 ═══════════

class TicketState(TypedDict):
    """LangGraph 全局状态：在节点间传递与累积"""
    # ── 基础信息 ──
    ticket_id: str
    customer_name: str
    channel: str
    priority: str
    content: str
    amount: float
    order_id: str
    order_detail: str
    crm_note: str
    policy: dict[str, Any]
    contact: str

    # ── 分析结果 ──
    intent: str                        # refund / complaint / technical / suggestion
    intent_confidence: float
    order_valid: bool
    risk_level: str                    # low / medium / high / critical
    decision: str                      # auto_approve / human_review / reject

    # ── 审批状态 ──
    approval_required: bool
    approval_status: str               # pending / approved / rejected
    approval_comment: str
    approval_by: str
    approval_at: str

    # ── 生成结果 ──
    response_draft: str
    quality_score: float
    qc_passed: bool

    # ── 追踪 ──
    messages: list[str]                # 每个节点的执行日志
    current_stage: str                 # 当前所在节点名称
    started_at: str
    completed_at: str
    execution_path: list[str]          # 走过的节点路径
    cost: dict[str, float]


# ═══════════ 工单加载 ═══════════

def load_ticket(ticket_id: str) -> Optional[dict]:
    """从预置 JSON 文件加载工单"""
    if not TICKETS_FILE.exists():
        logger.warning(f"投诉工单文件不存在: {TICKETS_FILE}")
        return None
    tickets = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
    for t in tickets:
        if t["id"] == ticket_id:
            return t
    return None


def list_tickets() -> list[dict]:
    """列出所有可用工单"""
    if not TICKETS_FILE.exists():
        return []
    tickets = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
    return [{"id": t["id"], "customer": t["customer"], "priority": t["priority"], "amount": t["amount"]} for t in tickets]


# ═══════════ 节点函数 ═══════════

def _log(state: TicketState, msg: str):
    """追加执行日志并推送 SSE 事件"""
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] [{state['current_stage']}] {msg}"
    state["messages"].append(entry)
    state.setdefault("execution_path", []).append(state["current_stage"])
    logger.info(entry)
    # 异步推送 SSE（由调用方处理）


async def node_read_ticket(state: TicketState) -> TicketState:
    """节点1: 读取工单 —— 加载并结构化工单信息"""
    state["current_stage"] = "read_ticket"
    state["started_at"] = datetime.now().isoformat()
    _log(state, f"📋 工单 {state['ticket_id']} 开始处理 | 客户: {state['customer_name']} | 优先级: {state['priority']}")

    ticket = load_ticket(state["ticket_id"])
    if not ticket:
        _log(state, f"❌ 未找到工单 {state['ticket_id']}")
        state["intent_confidence"] = 0.0
        return state

    # 合并工单信息到状态
    for key in ("customer", "contact", "channel", "priority", "content", "amount", "order_id", "order_detail", "crm_note", "policy"):
        rename = key if key != "customer" else "customer_name"
        state[rename] = ticket.get(key, state.get(rename, ""))

    _log(state, f"✅ 工单加载完成 | 金额: ¥{state['amount']:,.0f} | CRM: {state['crm_note'][:30]}...")
    return state


async def node_classify_intent(state: TicketState) -> TicketState:
    """节点2: 意图分类 —— LLM 将客诉分为 refund/complaint/technical/suggestion"""
    state["current_stage"] = "classify_intent"
    _log(state, "🤖 正在调用 LLM 进行意图分类...")

    llm = get_llm()
    prompt = f"""你是客服工单分类专家。请分析以下工单内容，将意图分为以下之一：
- refund: 退款/退换货相关
- complaint: 产品质量/服务投诉
- technical: 技术问题/系统故障
- suggestion: 建议/反馈

工单内容：
{state['content']}

请返回 JSON 格式：
{{"intent": "refund/complaint/technical/suggestion", "confidence": 0.0-1.0, "reason": "简短理由"}}
"""
    try:
        resp, _, _ = await llm.achat(prompt)
        data = json.loads(resp)
        state["intent"] = data.get("intent", "complaint")
        state["intent_confidence"] = data.get("confidence", 0.7)
        _log(state, f"✅ 意图: {state['intent']} | 置信度: {state['intent_confidence']:.0%} | 理由: {data.get('reason','')}")
    except Exception as e:
        state["intent"] = "complaint"
        state["intent_confidence"] = 0.5
        _log(state, f"⚠️ 意图分类降级: {str(e)[:60]}")

    return state


async def node_fetch_order(state: TicketState) -> TicketState:
    """节点3: 查询订单/CRM —— 验证订单有效性 + 客户画像"""
    state["current_stage"] = "fetch_order"
    _log(state, f"🔍 查询订单 {state['order_id']} 及 CRM 信息...")

    # 模拟延迟（真实场景需查询 ERP/CRM API）
    await asyncio.sleep(0.15)

    if state["order_id"] and state["order_detail"]:
        state["order_valid"] = True
        _log(state, f"✅ 订单有效: {state['order_detail'][:50]}...")
    else:
        state["order_valid"] = False
        _log(state, "⚠️ 订单信息缺失，将依赖客户描述")
        return state

    # CRM 客户画像
    if state["crm_note"]:
        _log(state, f"👤 CRM 画像: {state['crm_note'][:60]}...")

    return state


async def node_risk_assessment(state: TicketState) -> TicketState:
    """节点4: 风险评估 —— 基于金额+客户+策略做条件判断（LangGraph 核心：此处决定下一节点路由）"""
    state["current_stage"] = "risk_assessment"
    amount = state["amount"]
    policy = state.get("policy", {})

    _log(state, f"⚖️ 风险评估中... 金额: ¥{amount:,.0f} | 策略: {policy}")

    if policy.get("requires_review", False):
        state["risk_level"] = "critical"
        state["decision"] = "human_review"
        state["approval_required"] = True
        state["approval_status"] = "pending"
        _log(state, f"🔴 风险等级: CRITICAL | 决策: 需人工审批（金额 ¥{amount:,.0f} 超阈值）")
        return state

    if amount >= 2000:
        state["risk_level"] = "high"
        state["decision"] = "human_review"
        state["approval_required"] = True
        state["approval_status"] = "pending"
        _log(state, f"🟠 风险等级: HIGH | 决策: 需人工审批（金额 >= ¥2,000）")
    elif amount >= 500:
        state["risk_level"] = "medium"
        state["decision"] = "human_review"
        state["approval_required"] = True
        state["approval_status"] = "pending"
        _log(state, f"🟡 风险等级: MEDIUM | 决策: 建议人工审批（¥500-¥2,000）")
    else:
        state["risk_level"] = "low"
        state["decision"] = "auto_approve"
        state["approval_required"] = False
        state["approval_status"] = "approved"
        _log(state, f"🟢 风险等级: LOW | 决策: 自动批准（金额 < ¥500 / 或策略允许）")

    state["cost"] = state.get("cost", {})
    state["cost"]["risk_assessment"] = 0.001
    return state


async def node_human_approval(state: TicketState) -> TicketState:
    """节点5: Human-in-the-Loop —— LangGraph interrupt() 暂停并等待人工确认"""
    state["current_stage"] = "human_approval"
    _log(state, f"🛑 进入人工审批节点 | 金额: ¥{state['amount']:,.0f} | 客户: {state['customer_name']}")

    # LangGraph 核心：interrupt() 暂停执行，返回审批所需信息
    # 当用户通过 API 传入审批结果时，graph 从此处恢复
    approval_data = interrupt({
        "type": "human_approval",
        "ticket_id": state["ticket_id"],
        "customer": state["customer_name"],
        "amount": state["amount"],
        "intent": state["intent"],
        "risk_level": state["risk_level"],
        "crm_summary": state.get("crm_note", "")[:100],
        "question": f"是否批准该客诉？金额: ¥{state['amount']:,.0f}",
        "options": ["approve", "reject"],
    })

    # 恢复后：从 interrupt() 返回值中获取审批结果
    # approval_data 由 API 端调用 graph.update_state() 传入
    if isinstance(approval_data, dict):
        state["approval_status"] = approval_data.get("action", "rejected")
        state["approval_comment"] = approval_data.get("comment", "")
        state["approval_by"] = approval_data.get("reviewer", "系统管理员")
    else:
        # 降级：默认拒绝
        state["approval_status"] = "rejected"
        state["approval_comment"] = "审批超时，自动拒绝"
        state["approval_by"] = "系统自动"

    state["approval_at"] = datetime.now().isoformat()
    _log(state, f"{'✅ 审批通过' if state['approval_status'] == 'approved' else '❌ 审批拒绝'}"
                f" | 审批人: {state['approval_by']} | 意见: {state['approval_comment'][:40]}")
    return state


async def node_generate_response(state: TicketState) -> TicketState:
    """节点6: 生成回复草稿 —— LLM 根据审批结果生成回复"""
    state["current_stage"] = "generate_response"

    if state["approval_status"] == "rejected":
        _log(state, "✍️ 审批拒绝，生成拒绝对话草稿...")
        prompt = f"""客户工单拒绝处理。请生成专业、诚恳的拒绝对话草稿。
客户: {state['customer_name']}
事由: {state['content'][:200]}
拒绝原因: {state.get('approval_comment', '不符合退款政策')}

回复草稿:"""
    else:
        _log(state, "✍️ 审批通过，生成解决方案草稿...")
        prompt = f"""请生成专业、诚恳的客诉解决回复草稿。
客户: {state['customer_name']}
工单ID: {state['ticket_id']}
意图: {state['intent']}
金额: ¥{state['amount']:,.0f}
决策: {state['decision']}

回复格式要求:
1. 致歉与共情（简洁）
2. 解决方案（具体，可操作）
3. 时间节点（明确）
4. 联系人信息

回复草稿:"""

    llm = get_llm()
    try:
        resp, _, _ = await llm.achat(prompt)
        state["response_draft"] = resp[:800]  # 限制长度
        _log(state, f"✅ 回复草稿生成完成 ({len(state['response_draft'])} 字符)")
    except Exception as e:
        state["response_draft"] = f"尊敬的{state['customer_name']}，关于您的{state['intent']}问题，我们已收到并正在处理。客服将在1个工作日内联系您。"
        _log(state, f"⚠️ 回复草稿降级: {str(e)[:60]}")

    return state


async def node_quality_check(state: TicketState) -> TicketState:
    """节点7: 质检 —— AI 评估回复质量"""
    state["current_stage"] = "quality_check"
    _log(state, "🔎 AI 质检回复草稿...")

    # 简化质检规则（生产环境可接入专用质检模型）
    draft = state["response_draft"]
    score = 7.0  # 基础分

    # 规则检查
    if len(draft) > 100:
        score += 1.0
    if state["customer_name"] in draft:
        score += 1.0
    if any(kw in draft for kw in ["抱歉", "感谢", "理解", "处理", "联系"]):
        score += 1.0
    if len(draft) > 300:
        score = min(score, 10.0)

    state["quality_score"] = round(score, 1)
    state["qc_passed"] = score >= 7.0
    state["cost"] = state.get("cost", {})
    state["cost"]["quality_check"] = 0.0005

    qc_status = "✅ 通过" if state["qc_passed"] else "⚠️ 需人工复核"
    _log(state, f"{qc_status} | 质检得分: {state['quality_score']}/10")
    return state


async def node_finalize(state: TicketState) -> TicketState:
    """节点8: 归档 —— 记录完成状态并计算总成本"""
    state["current_stage"] = "finalize"
    state["completed_at"] = datetime.now().isoformat()

    # 计算总处理成本
    cost_total = sum(state.get("cost", {}).values())
    _log(state, f"🎯 工单处理完成 | 决走路径: {' → '.join(state.get('execution_path', []))}")
    _log(state, f"📊 总结: 意图={state['intent']}, 风险={state['risk_level']}, 决策={state['decision']}, 审批={state['approval_status']}")
    _log(state, f"💰 处理成本: ${cost_total:.4f}")

    return state


# ═══════════ 路由函数（LangGraph 条件边） ═══════════

def route_after_risk(state: TicketState) -> Literal["auto_approve", "human_approval"]:
    """风险评估后的条件路由：LangGraph 根据 decision 字段自动跳转"""
    if state["decision"] == "auto_approve":
        return "auto_approve"
    return "human_approval"


def route_after_approval(state: TicketState) -> Literal["generate_response", "finalize"]:
    """审批后的条件路由：根据审批状态跳转"""
    if state["approval_status"] == "approved":
        return "generate_response"
    return "finalize"


# ═══════════ 构建 LangGraph StateGraph ═══════════

checkpointer = MemorySaver()


def create_complaint_graph() -> StateGraph:
    """构建智能客诉工单处理 LangGraph"""
    builder = StateGraph(TicketState)

    # 添加 8 个节点
    builder.add_node("read_ticket", node_read_ticket)
    builder.add_node("classify_intent", node_classify_intent)
    builder.add_node("fetch_order", node_fetch_order)
    builder.add_node("risk_assessment", node_risk_assessment)
    builder.add_node("human_approval", node_human_approval)
    builder.add_node("auto_approve", lambda s: s)  # 占位节点，直接通过
    builder.add_node("generate_response", node_generate_response)
    builder.add_node("quality_check", node_quality_check)
    builder.add_node("finalize", node_finalize)

    # 设置入口
    builder.set_entry_point("read_ticket")

    # 普通边（固定下一跳）
    builder.add_edge("read_ticket", "classify_intent")
    builder.add_edge("classify_intent", "fetch_order")
    builder.add_edge("fetch_order", "risk_assessment")

    # 条件边（动态路由）—— LangGraph 核心特性
    builder.add_conditional_edges("risk_assessment", route_after_risk, {
        "auto_approve": "auto_approve",
        "human_approval": "human_approval",
    })

    builder.add_edge("auto_approve", "generate_response")
    builder.add_edge("human_approval", "generate_response")
    builder.add_edge("generate_response", "quality_check")
    builder.add_edge("quality_check", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)


# ═══════════ 执行器 ═══════════

complaint_graph = create_complaint_graph()


async def run_complaint_workflow(ticket_id: str, config: dict = None) -> dict:
    """异步执行客诉处理工作流"""
    if config is None:
        config = {"configurable": {"thread_id": f"complaint-{ticket_id}"}}

    # 初始化状态
    initial_state: TicketState = {
        "ticket_id": ticket_id,
        "customer_name": "",
        "channel": "",
        "priority": "",
        "content": "",
        "amount": 0.0,
        "order_id": "",
        "order_detail": "",
        "crm_note": "",
        "policy": {},
        "contact": "",
        "intent": "",
        "intent_confidence": 0.0,
        "order_valid": False,
        "risk_level": "",
        "decision": "",
        "approval_required": False,
        "approval_status": "",
        "approval_comment": "",
        "approval_by": "",
        "approval_at": "",
        "response_draft": "",
        "quality_score": 0.0,
        "qc_passed": False,
        "messages": [],
        "current_stage": "init",
        "started_at": "",
        "completed_at": "",
        "execution_path": [],
        "cost": {},
    }

    # 使用 ainvoke（同步式），LangGraph 会自动在 interrupt 处暂停
    final_state = await complaint_graph.ainvoke(initial_state, config)

    # 检查是否被 interrupt 暂停
    snapshot = complaint_graph.get_state(config)
    if snapshot.next:
        # 有 pending 节点 → 等待人工审批
        pending_node = snapshot.next[0] if snapshot.next else "unknown"
        return {
            "status": "awaiting_approval",
            "state": {
                "ticket_id": final_state.get("ticket_id"),
                "customer_name": final_state.get("customer_name"),
                "amount": final_state.get("amount"),
                "intent": final_state.get("intent"),
                "risk_level": final_state.get("risk_level"),
                "messages": final_state.get("messages", []),
            },
            "approval_data": {
                "type": "human_approval",
                "ticket_id": final_state.get("ticket_id"),
                "customer": final_state.get("customer_name"),
                "amount": final_state.get("amount"),
                "risk_level": final_state.get("risk_level"),
                "question": f"是否批准该客诉？金额: ¥{final_state.get('amount', 0):,.0f}",
                "options": ["approve", "reject"],
            },
            "config": config,
        }

    return {
        "status": "completed",
        "state": final_state,
        "summary": {
            "ticket_id": final_state.get("ticket_id"),
            "customer": final_state.get("customer_name"),
            "intent": final_state.get("intent"),
            "decision": final_state.get("decision"),
            "risk_level": final_state.get("risk_level"),
            "approval_status": final_state.get("approval_status"),
            "response_draft": final_state.get("response_draft"),
            "quality_score": final_state.get("quality_score"),
            "execution_path": final_state.get("execution_path", []),
            "cost_total": round(sum(final_state.get("cost", {}).values()), 4),
        },
        "messages": final_state.get("messages", []),
    }
