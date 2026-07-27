import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { RadarChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';
import { useWorkflowStore } from '@/store/workflowStore';

echarts.use([RadarChart, TooltipComponent, CanvasRenderer]);

/** CLEAR 评估雷达图：成本 / 延迟 / 效能 / 保证 / 可靠性（0-100） */
export default function ClearRadar() {
  const clearScores = useWorkflowStore((s) => s.clearScores);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);

  // 初始化 / 销毁图表实例
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  // 评分变化时更新数据
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !clearScores) return;
    const option: EChartsCoreOption = {
      tooltip: { trigger: 'item' },
      radar: {
        indicator: [
          { name: '成本', max: 100 },
          { name: '延迟', max: 100 },
          { name: '效能', max: 100 },
          { name: '保证', max: 100 },
          { name: '可靠性', max: 100 },
        ],
        radius: '68%',
        center: ['50%', '52%'],
        axisName: {
          color: '#475569',
          fontSize: 12,
          fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif',
        },
        splitArea: {
          areaStyle: {
            color: ['#ffffff', '#f8fafc'],
          },
        },
        splitLine: { lineStyle: { color: '#e2e8f0' } },
        axisLine: { lineStyle: { color: '#e2e8f0' } },
      },
      series: [
        {
          type: 'radar',
          data: [
            {
              name: 'CLEAR 评分',
              value: [
                clearScores.cost,
                clearScores.latency,
                clearScores.efficacy,
                clearScores.assurance,
                clearScores.reliability,
              ],
              symbol: 'circle',
              symbolSize: 5,
              lineStyle: { color: '#6366f1', width: 2 },
              itemStyle: { color: '#6366f1' },
              areaStyle: { color: 'rgba(99, 102, 241, 0.18)' },
            },
          ],
        },
      ],
    };
    chart.setOption(option, { notMerge: true });
  }, [clearScores]);

  return (
    <section className="card">
      <div className="card-header">
        <div className="card-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          CLEAR 评估
        </div>
        {clearScores && (
          <span className="badge badge-indigo">效能 {clearScores.efficacy.toFixed(1)}</span>
        )}
      </div>
      <div className="card-body">
        {clearScores ? (
          <div ref={containerRef} className="radar-wrap" />
        ) : (
          <div className="radar-empty">
            <span style={{ fontSize: 26 }}>📊</span>
            暂无 CLEAR 评估数据
            <span className="text-tertiary" style={{ fontSize: 11.5 }}>
              工作流完成后自动生成五维评分
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
