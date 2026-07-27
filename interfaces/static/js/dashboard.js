/* ═══════════════════════════════════════════
   dashboard.js — AgentForge Orchestrator 工具库
   ═══════════════════════════════════════════ */

/**
 * 文字解码动画（仅在拆解和故障注入时触发）
 * 模仿 React Bits 的 DecodeText 效果，纯原生 JS 实现
 */
function decodeText(element, targetText, durationMs = 600) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const original = element.textContent;
  const startTime = performance.now();
  let frame;

  function animate(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / durationMs, 1);

    // 已解码的字符数
    const revealedCount = Math.floor(progress * targetText.length);
    let result = '';

    for (let i = 0; i < targetText.length; i++) {
      if (i < revealedCount) {
        result += targetText[i];
      } else if (targetText[i] === ' ' || targetText[i] === '\n') {
        result += ' ';
      } else {
        result += chars[Math.floor(Math.random() * chars.length)];
      }
    }

    element.textContent = result;
    element.classList.add('decode-active');

    if (progress < 1) {
      frame = requestAnimationFrame(animate);
    } else {
      element.textContent = targetText;
      element.classList.remove('decode-active');
    }
  }

  frame = requestAnimationFrame(animate);
  return () => cancelAnimationFrame(frame);
}

/**
 * 格式化耗时
 */
function formatDuration(seconds) {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
}

/**
 * 格式化时间戳
 */
function formatTime(ts) {
  const d = ts ? new Date(ts * 1000) : new Date();
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}

/**
 * 默认 CLEAR 雷达图配置
 */
function createRadarOption(values, name = 'CLEAR 评估') {
  return {
    radar: {
      indicator: [
        { name: '成本 Cost', max: 100 },
        { name: '延迟 Latency', max: 100 },
        { name: '效能 Efficacy', max: 100 },
        { name: '保证 Assurance', max: 100 },
        { name: '可靠性 Reliability', max: 100 },
      ],
      shape: 'circle',
      center: ['50%', '50%'],
      radius: '65%',
      axisName: { color: '#64748b', fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(99,102,241,0.02)', 'rgba(99,102,241,0.04)'] } },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
    },
    series: [{
      type: 'radar',
      data: [{ value: values || [0, 0, 0, 0, 0], name }],
      areaStyle: { color: 'rgba(99,102,241,0.15)' },
      lineStyle: { color: '#6366f1', width: 2 },
      itemStyle: { color: '#6366f1' },
    }],
  };
}

/**
 * 日志条目
 */
function createLogEntry(level, icon, message) {
  const div = document.createElement('div');
  div.className = `log-entry log-${level}`;
  div.innerHTML = `
    <span class="log-time">[${formatTime()}]</span>
    <span class="log-icon">${icon}</span>
    <span class="log-msg">${message}</span>
  `;
  return div;
}
