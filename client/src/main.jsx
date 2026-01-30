import React, { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("未捕获错误:", error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', color: '#c0392b', fontFamily: 'monospace', background: '#fff' }}>
          <h1>发生错误。</h1>
          <h3 style={{ color: '#e74c3c' }}>{this.state.error && this.state.error.toString()}</h3>
          <details style={{ whiteSpace: 'pre-wrap', marginTop: '10px' }}>
            {this.state.errorInfo && this.state.errorInfo.componentStack}
          </details>
        </div>
      );
    }

    return this.props.children;
  }
}

async function mountApp() {
  const rootElement = document.getElementById('root');
  if (!rootElement) {
    throw new Error("未找到根节点");
  }
  const mod = await import('./App.jsx');
  const App = mod.default;
  if (!App) {
    throw new Error("未找到应用模块");
  }
  createRoot(rootElement).render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>,
  )
}

mountApp().catch((e) => {
  document.body.innerHTML = `<div style="color:red; font-size: 24px; padding: 20px;">
    <h1>启动错误</h1>
    <pre>${e.toString()}</pre>
    <pre>${e.stack}</pre>
  </div>`;
  console.error("启动失败:", e);
});
