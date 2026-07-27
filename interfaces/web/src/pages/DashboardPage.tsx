import ClearRadar from '@/components/ClearRadar';
import LogStream from '@/components/LogStream';
import MetricCards from '@/components/MetricCards';
import NewTaskPanel from '@/components/NewTaskPanel';
import ServiceTopology from '@/components/ServiceTopology';
import TaskFlowView from '@/components/TaskFlowView';

/**
 * 总控台（核心页）：三栏 Grid
 * 左栏 新建任务 + 服务拓扑 ｜ 中栏 任务执行流 ｜ 右栏 CLEAR 评估 + 指标卡 + 实时日志
 */
export default function DashboardPage() {
  return (
    <div>
      <h1 className="page-title">总控台</h1>
      <p className="page-desc">提交任务、监控多智能体编排执行过程与 CLEAR 五维评估</p>

      <div className="console-grid">
        <div className="console-col">
          <NewTaskPanel />
          <ServiceTopology />
        </div>

        <div className="console-col">
          <TaskFlowView />
        </div>

        <div className="console-col">
          <ClearRadar />
          <MetricCards />
          <LogStream />
        </div>
      </div>
    </div>
  );
}
