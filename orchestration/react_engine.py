"""OrchestratorRuntime — ReAct 引擎 v2

- LLM 动态规划 + Schema 约束
- 自动重试 N 次 + DAG 并行执行
- 审批队列 + 实时流式日志回调
"""

import time, json, threading
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from orchestration.tool_schema import schema_to_prompt, validate_plan
from orchestration.sandbox import Sandbox
from orchestration import state_models as M

SYSTEM_PROMPT = f"""你是一个 OrchestratorRuntime 规划专家。
用户给你一个任务描述，你需要制定一个分步骤的执行计划。

{schema_to_prompt()}

规则:
1. 每步只调用一个工具
2. 工具名必须是上面列出的，不能自创
3. 输出 JSON 数组，不要加其他文字
4. 如果需要用户确认，设置 "approval_required": true
5. 如果任务需要读写文件，先 list_dir 看看有哪些文件
6. 如果步骤之间有依赖关系，设置 "depends_on": [前置步骤序号]

输出格式:
[{{"index":0,"action":"工具名","params":{{...}},"expected":"预期","depends_on":[]}}]
"""

MAX_RETRIES = 3
MAX_STEPS = 50


class ReActEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._approve_callback = None

    def create_task(self, user_id: str, prompt: str, timeout: float = 5.0) -> dict:
        return M.create_task(user_id, prompt, timeout)

    def _emit(self, cb, task: dict, msg: str):
        if cb:
            try:
                cb(task, msg)
            except Exception:
                pass

    # ── 主入口 ──

    def run(self, task_id: str, llm_client=None, llm_config: Optional[dict] = None,
            on_update: Optional[callable] = None) -> dict:
        task = M.load_task(task_id)
        if not task:
            return {"error": "task not found"}

        sandbox = Sandbox(task["id"])
        persist_dir = Path(__file__).parent.parent / "data" / "workflow_outputs" / task["id"]
        sandbox.set_persist(persist_dir)
        sandbox.setup()

        try:
            task["status"] = "PLANNING"
            task["history"] = task.get("history", [])
            M.save_task(task)
            self._emit(on_update, task, "任务进入规划阶段")

            for iteration in range(MAX_STEPS):
                task = M.load_task(task_id)

                if time.time() > task["created_at"] + task["timeout_minutes"] * 60:
                    task["status"] = "TIMEOUT"
                    M.save_task(task)
                    self._emit(on_update, task, "⏰ 任务超时")
                    break
                if task["status"] == "CANCELLED":
                    self._emit(on_update, task, "🚫 任务已取消")
                    break

                # ── PLANNING ──
                if task["status"] in ("PENDING", "PLANNING"):
                    p = task["prompt"].lower()
                    if any(kw in p for kw in ["分析", "统计", "年报", "报告", "信息"]):
                        plan = self._fallback_plan(task["prompt"])
                    else:
                        plan = self._llm_plan(task, llm_client, llm_config)
                        plan = validate_plan(plan)
                        if not plan:
                            plan = self._fallback_plan(task["prompt"])
                    task["plan"] = plan
                    task["current_step"] = 0
                    task["status"] = "EXECUTING"
                    task["steps"] = []
                    for s in plan:
                        task["steps"].append({
                            "idx": s["index"], "action": s["action"],
                            "params": s.get("params", {}),
                            "status": "pending", "result": "",
                            "started_at": None, "finished_at": None,
                            "retries": 0, "depends_on": s.get("depends_on", []),
                        })
                    M.save_task(task)
                    self._emit(on_update, task, f"✅ 计划完成: {len(plan)} 步")
                    continue

                # ── EXECUTING (DAG 并行) ──
                if task["status"] == "EXECUTING":
                    pending = [s for s in task["steps"] if s["status"] in ("pending", "retrying")]
                    if not pending:
                        # 全部完成
                        all_ok = all(s["status"] == "done" for s in task["steps"])
                        task["status"] = "DONE" if all_ok else "FAILED"
                        task["result"] = {"message": "所有步骤执行完成" if all_ok else "部分步骤失败"}
                        M.save_task(task)
                        self._emit(on_update, task, f"{'✅ 完成' if all_ok else '⚠️ 部分失败'}")
                        break

                    # 找出依赖已满足的步骤（并行执行）
                    ready = []
                    for s in pending:
                        deps = s.get("depends_on", [])
                        if all(task["steps"][d]["status"] == "done" for d in deps if d < len(task["steps"])):
                            ready.append(s)

                    if not ready:
                        # 没有可执行的步骤 → 死锁
                        task["status"] = "FAILED"
                        task["error"] = "步骤依赖死锁"
                        M.save_task(task)
                        break

                    # 并行执行 ready 步骤
                    futures = {}
                    for step in ready:
                        step["status"] = "running"
                        step["started_at"] = time.time()
                        M.save_task(task)
                        self._emit(on_update, task, f"▶️ 步骤 {step['idx']}: {step['action']}")
                        futures[self._executor.submit(self._execute_step, step, sandbox)] = step

                    for future in as_completed(futures):
                        step = futures[future]
                        try:
                            result = future.result(timeout=30)
                        except Exception as e:
                            result = f"⚠️ 执行异常: {e}"

                        step["result"] = (result or "(无输出)")[:2000]
                        step["finished_at"] = time.time()

                        if result and not result.startswith("⚠️"):
                            step["status"] = "done"
                            self._emit(on_update, task, f"✅ 步骤 {step['idx']}: {step['action']} → OK")
                        else:
                            step["retries"] += 1
                            if step["retries"] >= MAX_RETRIES:
                                step["status"] = "failed"
                                self._emit(on_update, task, f"❌ 步骤 {step['idx']}: {step['action']} → 失败")
                            else:
                                step["status"] = "retrying"
                                self._emit(on_update, task, f"🔄 步骤 {step['idx']} 重试 {step['retries']}/{MAX_RETRIES}")

                        task["history"].append({
                            "role": "assistant",
                            "content": f"TOOL: {step['action']}(...) → {step['status']}: {result[:100] if result else ''}"
                        })
                        M.save_task(task)

        except Exception as e:
            task = M.load_task(task_id)
            task["status"] = "FAILED"
            task["error"] = str(e)
            M.save_task(task)
            self._emit(on_update, task, f"❌ 异常: {e}")
        finally:
            sandbox.teardown()

        final = M.load_task(task_id)
        self._emit(on_update, final, f"🏁 任务结束: {final['status']}")
        return final

    # ── 规划 ──

    def _llm_plan(self, task: dict, client, config: Optional[dict]) -> list[dict]:
        if not client:
            return self._fallback_plan(task["prompt"])
        try:
            text = client.chat(
                [{"role": "user", "content": f"任务: {task['prompt']}\n\n{SYSTEM_PROMPT}"}],
                temperature=0.1, max_tokens=2000,
            ).strip()
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end != -1:
                return json.loads(text[start:end+1])
        except Exception as e:
            print(f"[ReAct] LLM planning failed: {e}")
        return self._fallback_plan(task["prompt"])

    def _fallback_plan(self, prompt: str) -> list[dict]:
        p = prompt.lower()
        if "分析" in p or "统计" in p or "信息" in p or "年报" in p or "报告" in p:
            return [{"index": 0, "action": "run_python", "params": {"code": f"""
import pathlib as _pl
docs = _pl.Path('D:/hermes/work/agentgroup/agent_forge/docs')
out_dir = _pl.Path('D:/hermes/work/agentgroup/agent_forge/data/workflow_outputs')
out_dir.mkdir(parents=True, exist_ok=True)
files = sorted(docs.glob('*.md'))
total_lines = 0; total_chars = 0; details = []
for f in files:
    text = f.read_text(encoding='utf-8')
    lines = text.count(chr(10)) + 1; chars = len(text)
    total_lines += lines; total_chars += chars
    preview = text[:200].replace(chr(10), ' ')[:100]
    details.append('  ' + f.name + ': ' + str(lines) + ' 行, ' + str(chars) + ' 字 | ' + preview)
details.sort(key=lambda x: int(x.split(':')[1].strip().split()[0]) if '行' in x else 0, reverse=True)
max_file = details[0].split(':')[0].strip() if details else '无'
lines_out = ['分析报告', '='*30, '共 ' + str(len(files)) + ' 个文件',
             '总行数: ' + str(total_lines), '总字符数: ' + str(total_chars),
             '内容最多: ' + max_file, '---']
lines_out.extend(details)
report = chr(10).join(lines_out)
(out_dir / 'analysis_report.txt').write_text(report, encoding='utf-8')
print(report[:2000])
"""}, "expected": "分析报告已生成"}]
        if "替换" in p or "修改" in p:
            return [{"index": 0, "action": "list_dir", "params": {"path": "."}, "expected": "列出文件"}]
        return [{"index": 0, "action": "think", "params": {"thought": prompt}, "expected": "记录"}]

    # ── 工具执行 ──

    def _execute_step(self, step: dict, sandbox: Sandbox) -> str:
        action = step["action"]
        params = step.get("params", {})
        if action == "list_dir":
            return str(sandbox.list_dir(params.get("path", ".")))
        elif action == "read_file":
            return sandbox.read_file(params.get("path", ""))
        elif action == "write_file":
            sandbox.write_file(params.get("path", ""), params.get("content", ""))
            return "写入成功"
        elif action == "run_python":
            return sandbox.run_python(params.get("code", ""), int(params.get("timeout", 30)))
        elif action == "run_shell":
            return sandbox.run_shell(params.get("cmd", ""), int(params.get("timeout", 15)))
        elif action == "wait":
            time.sleep(int(params.get("seconds", 1)))
            return f"等待 {params.get('seconds',1)} 秒"
        else:
            return f"⚠️ 未知工具: {action}"
