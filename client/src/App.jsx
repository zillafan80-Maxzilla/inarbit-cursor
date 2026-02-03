/**
 * Inarbit HFT System - 主应用入口
 * 灰绿色主题 UI 重构版 v4.0
 */
import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom'

// 页面组件
import ControlPanel from './pages/ControlPanel'
import Logs from './pages/Logs'
import LivePrices from './pages/LivePrices'
import PnLOverview from './pages/PnLOverview'
import SimulationConfig from './pages/SimulationConfig'
import Portfolio from './pages/Portfolio'
import ExchangeAssets from './pages/ExchangeAssets'
import UserManagement from './pages/UserManagement'
import Strategies from './pages/Strategies'
import Settings from './pages/Settings'
import ExchangeManagement from './pages/ExchangeManagement'
import ExchangePairs from './pages/ExchangePairs'
import RiskDashboard from './pages/RiskDashboard'
import Login from './pages/Login'
import SystemOverview from './pages/SystemOverview'
import DecisionConsole from './pages/DecisionConsole'
import ArbitrageMonitor from './pages/ArbitrageMonitor'
import ConfigCatalog from './pages/ConfigCatalog'
import AdminHub from './pages/AdminHub'
import RealtimeOverview from './pages/RealtimeOverview'

import OmsConsole from './pages/OmsConsole'
import BotConsole from './pages/BotConsole'
import Scanners from './pages/Scanners'

import { getAuthToken, configAPI, authAPI, setAuthToken } from './api/client'

import './App.css'


// 全局顶部边条
const GlobalHeader = ({ botStatus, tradingMode, liveEnabled }) => (
  <header className="global-header">
    <div className="header-logo">
      <div className="logo-icon">📊</div>
      <span>因纳比特</span>
    </div>
    <div className="header-info">
      <div className="header-status">
        <span className="status-indicator" style={{
          backgroundColor: botStatus === 'running' ? '#00b894' : '#b2bec3'
        }}></span>
        <span>{botStatus === 'running' ? '系统运行中' : '系统已停止'}</span>
      </div>
      <span>{tradingMode === 'live' ? '🔴 实盘' : '🟢 模拟'} · {liveEnabled ? '实盘已启用' : '实盘已禁用'}</span>
      <span>版本 4.0.0 高频核心</span>
    </div>
  </header>
);

// 全局底部边条
const GlobalFooter = () => (
  <footer className="global-footer">
    <div className="footer-left">
      <span>© 2026 因纳比特交易系统</span>
      <span>•</span>
      <span>高频交易引擎</span>
    </div>
    <div className="footer-right">
      <span>技术栈：高性能引擎 + 服务端 + 前端框架</span>
    </div>
  </footer>
);

// 侧边栏导航组件 (重构版 - 简洁风格 + 可拖动调整宽度)
const Sidebar = ({ tradingMode, botStatus, currentUser }) => {
  const location = useLocation();
  const isActive = (path) => location.pathname === path ? 'active' : '';
  const isAdmin = currentUser?.role === 'admin';
  
  // 侧边栏宽度拖动调整
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('sidebar_width');
    return saved ? parseInt(saved) : 360;
  });
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    if (!isResizing) {
      document.body.classList.remove('resizing-sidebar');
      return;
    }

    document.body.classList.add('resizing-sidebar');

    const handleMouseMove = (e) => {
      const newWidth = Math.max(200, Math.min(600, e.clientX));
      setSidebarWidth(newWidth);
      localStorage.setItem('sidebar_width', newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.body.classList.remove('resizing-sidebar');
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.classList.remove('resizing-sidebar');
    };
  }, [isResizing]);
  

  // 菜单配置
  const menuGroups = [
    {
      title: '管理总览',
      items: [
        { path: '/admin', icon: '🗺️', label: '管理总览' },
        { path: '/realtime', icon: '📊', label: '实时总览', showStatus: true },
        { path: '/control', icon: '🎛️', label: '控制面板' },
        { path: '/system', icon: '🧭', label: '系统概览' },
      ]
    },
    {
      title: '执行与调度',
      items: [
        { path: '/oms', icon: '🧩', label: '订单管理控制' },
        { path: '/scanners', icon: '🔍', label: '扫描器参数', adminOnly: true },
        { path: '/decision', icon: '🧠', label: '决策管理' },
        { path: '/arbitrage', icon: '🧪', label: '套利机会' },
      ]
    },
    {
      title: '市场与资产',
      items: [
        { path: '/live-prices', icon: '📈', label: '实时价格' },
        { path: '/pnl', icon: '💰', label: '收益展示' },
        { path: '/portfolio', icon: '📦', label: '模拟持仓' },
        { path: '/live-assets', icon: '🏦', label: '交易所账户' },
      ]
    },
    {
      title: '交易所与策略',
      items: [
        { path: '/exchanges', icon: '🔗', label: '交易所管理' },
        { path: '/exchange-pairs', icon: '🧩', label: '交易对管理' },
        { path: '/strategies', icon: '🎯', label: '策略管理' },
        { path: '/config-catalog', icon: '🗂️', label: '配置目录' },
      ]
    },
    {
      title: '风险与权限',
      items: [
        { path: '/risk', icon: '🛡️', label: '风险监控', adminOnly: true },
        { path: '/settings', icon: '⚙️', label: '全局设置' },
        { path: '/sim-config', icon: '⚙️', label: '模拟配置' },
        { path: '/logs', icon: '📋', label: '运行日志' },
        { path: '/user', icon: '👤', label: '账户与密钥' },
      ]
    },
  ];

  const visibleMenuGroups = menuGroups
    .map((group) => ({
      ...group,
      items: (group.items || []).filter((item) => !item.adminOnly || isAdmin),
    }))
    .filter((group) => (group.items || []).length > 0);

  return (
    <aside className="sidebar" style={{ width: `${sidebarWidth}px`, position: 'relative' }}>
      {/* 用户信息区域 */}
      <div className="sidebar-user">
        <div className="user-avatar">用</div>
        <div className="user-info">
          <div className="user-name">{currentUser?.username || '未登录'}</div>
          <div className="user-role">{currentUser?.role === 'admin' ? '管理员' : '用户'}</div>
        </div>
      </div>

      {/* 导航菜单 */}
      <nav className="sidebar-nav">
        {visibleMenuGroups.map((group, groupIndex) => (
          <div key={groupIndex} className="nav-group">
            <div className="nav-group-title">
              {group.title}
            </div>
            <div className="sub-nav">
              {group.items.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`nav-item ${isActive(item.path)}`}
                >
                  {item.showStatus && (
                    <span className={`status-dot ${botStatus}`}></span>
                  )}
                  <span className="nav-icon">{item.icon}</span>
                  <span>{item.label}</span>
                  {item.adminOnly && (
                    <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>Admin</span>
                  )}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* 底部模式指示器 */}
      <div className="mode-indicator">
        <div className="label">交易模式</div>
        <div className={`value ${tradingMode}`}>
          {tradingMode === 'live' ? '🔴 实盘' : '🟢 模拟'}
        </div>
      </div>
      
      {/* 可拖动分隔条 - 垂直边条，左右拖动调整宽度 */}
      <div 
        className="sidebar-resizer"
        onMouseDown={() => setIsResizing(true)}
      />
    </aside>
  );
};

function App() {
  // 全局状态
  const [botStatus, setBotStatus] = useState('running');
  const [tradingMode, setTradingMode] = useState('paper');
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const raw = localStorage.getItem('inarbit_user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [liveEnabled, setLiveEnabled] = useState(false);
  const authed = !!getAuthToken();
  const isAdmin = currentUser?.role === 'admin';

  const RequireAdmin = ({ children }) => {
    if (authed && !currentUser) {
      return (
        <div className="content-body">
          <div className="stat-box" style={{ padding: '12px' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '6px' }}>加载用户信息...</div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
              正在确认管理员权限，请稍候。
            </div>
          </div>
        </div>
      );
    }
    if (isAdmin) return children;
    return (
      <div className="content-body">
        <div className="page-header" style={{ marginBottom: '16px' }}>
          <div>
            <h1 className="page-title">需要管理员权限</h1>
            <p className="page-subtitle">当前账户无权限访问此页面</p>
          </div>
        </div>
        <div className="stat-box" style={{ padding: '12px' }}>
          <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '6px' }}>访问被拒绝</div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
            请使用管理员账号登录后再访问，或联系管理员为当前账号授予权限。
          </div>
        </div>
      </div>
    );
  };

  useEffect(() => {
    if (!getAuthToken()) return;
    let mounted = true;
    const loadSettings = async () => {
      try {
        const res = await configAPI.getGlobalSettings();
        if (!mounted) return;
        const data = res?.data || {};
        setTradingMode(data.tradingMode || 'paper');
        setBotStatus(data.botStatus || 'running');
        setLiveEnabled(!!data.liveEnabled);
      } catch {
        // ignore
      }
    };
    loadSettings();
    return () => { mounted = false; };
  }, [authed]);

  useEffect(() => {
    if (!getAuthToken()) return;
    let mounted = true;
    const loadUser = async () => {
      try {
        const res = await authAPI.me();
        const user = res?.user || null;
        if (!mounted) return;
        setCurrentUser(user);
        if (user) {
          localStorage.setItem('inarbit_user', JSON.stringify(user));
        }
      } catch {
        // token 可能已过期，保持 UI 可用但不强制跳转
        if (!mounted) return;
        setCurrentUser(null);
        setAuthToken(null);
        localStorage.removeItem('inarbit_user');
      }
    };
    loadUser();
    return () => { mounted = false; };
  }, [authed]);


  return (
    <Router>
      <div className="app-container">
        {/* 顶部灰绿色边条 */}
        <GlobalHeader botStatus={botStatus} tradingMode={tradingMode} liveEnabled={liveEnabled} />

        {/* 主体区域：侧边栏 + 内容 */}
        <div className="main-wrapper">
          <Sidebar botStatus={botStatus} tradingMode={tradingMode} currentUser={currentUser} />

          <main className="main-layout">
              <Routes>
                <Route path="/login" element={<Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/admin" element={authed ? <AdminHub currentUser={currentUser} /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                <Route path="/" element={
                  authed ? (
                    <Navigate to="/realtime" replace />
                  ) : (
                    <Login onLogin={(u) => setCurrentUser(u)} />
                  )
                } />
                <Route path="/realtime" element={authed ? <RealtimeOverview /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/control" element={
                  authed ? (
                    <ControlPanel
                      botStatus={botStatus}
                      setBotStatus={setBotStatus}
                      tradingMode={tradingMode}
                      setTradingMode={setTradingMode}
                    />
                  ) : (
                    <Login onLogin={(u) => setCurrentUser(u)} />
                  )
                } />
                <Route path="/logs" element={<Logs />} />
                <Route path="/system" element={authed ? <SystemOverview /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                {/* OMS */}
                <Route path="/bot" element={authed ? <Navigate to="/control" replace /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/oms" element={authed ? <OmsConsole /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/oms-config" element={authed ? <Navigate to="/oms" replace /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/scanners" element={authed ? <RequireAdmin><Scanners /></RequireAdmin> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/decision" element={authed ? <DecisionConsole /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/arbitrage" element={authed ? <ArbitrageMonitor /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                {/* 交易视图 */}
                <Route path="/live-prices" element={authed ? <LivePrices /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/pnl" element={authed ? <PnLOverview tradingMode={tradingMode} /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                {/* 模拟盘 */}
                <Route path="/portfolio" element={authed ? <Portfolio /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/sim-config" element={authed ? <SimulationConfig /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                {/* 实盘 */}
                <Route path="/live-assets" element={authed ? <ExchangeAssets /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                {/* 用户管理 */}
                <Route path="/user" element={authed ? <UserManagement /> : <Login onLogin={(u) => setCurrentUser(u)} />} />

                {/* 配置 */}
                <Route path="/strategies" element={authed ? <Strategies /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/exchanges" element={authed ? <ExchangeManagement /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/exchange-pairs" element={authed ? <ExchangePairs /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/config-catalog" element={authed ? <ConfigCatalog /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/settings" element={authed ? <Settings currentUser={currentUser} /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/risk" element={authed ? <RequireAdmin><RiskDashboard /></RequireAdmin> : <Login onLogin={(u) => setCurrentUser(u)} />} />
              </Routes>
          </main>
        </div>

        {/* 底部灰绿色边条 */}
        <GlobalFooter />
      </div>
    </Router>
  )
}

export default App
