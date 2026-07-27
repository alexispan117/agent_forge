import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

/** 路由出口级错误边界：渲染异常时展示中文错误页并支持重试 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, message: '' };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    const message = error instanceof Error ? error.message : String(error);
    return { hasError: true, message };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error('[ErrorBoundary] 页面渲染异常:', error, info.componentStack);
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false, message: '' });
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="card error-page">
        <div className="error-page-icon">⚠️</div>
        <div className="error-page-title">页面出现异常</div>
        <p className="text-tertiary" style={{ fontSize: 13, margin: 0 }}>
          界面渲染时发生错误，你的数据不受影响。可尝试重试，或刷新页面。
        </p>
        {this.state.message && (
          <div className="error-page-detail">{this.state.message}</div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          <button type="button" className="btn btn-primary" onClick={this.handleRetry}>
            重试
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </button>
        </div>
      </div>
    );
  }
}
