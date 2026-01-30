/**
 * Inarbit HFT System - 主应用入口
 * 灰绿色主题 UI 重构版 v4.0
 */
import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'

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

import OmsConsole from './pages/OmsConsole'
import OmsConfig from './pages/OmsConfig'

import { getAuthToken } from './api/client'

import './App.css'


// 全局顶部边条
const GlobalHeader = ({ botStatus }) => (
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

// 侧边栏导航组件 (重构版 - 简洁风格)
const Sidebar = ({ tradingMode, botStatus, currentUser }) => {
  const location = useLocation();
  const isActive = (path) => location.pathname === path ? 'active' : '';

  // 菜单配置
  const menuGroups = [
    {
      title: '运行中心',
      items: [
        { path: '/', icon: '🎛️', label: '控制面板', showStatus: true },
        { path: '/system', icon: '🧭', label: '系统概览' },
        { path: '/logs', icon: '📋', label: '运行日志' },
      ]
    },
    {
      title: '交易执行',
      items: [
        { path: '/oms', icon: '🧩', label: '订单管理控制台' },
        { path: '/oms-config', icon: '🧰', label: '订单管理参数' },
        { path: '/decision', icon: '🧠', label: '决策管理' },
        { path: '/arbitrage', icon: '🧪', label: '套利机会' },
      ]
    },
    {
      title: '数据视图',
      items: [
        { path: '/live-prices', icon: '📈', label: '实时价格' },
        { path: '/pnl', icon: '💰', label: '收益展示' },
      ]
    },
    {
      title: '资产与模拟',
      items: [
        { path: '/sim-config', icon: '⚙️', label: '模拟配置' },
        { path: '/portfolio', icon: '📦', label: '模拟持仓' },
        { path: '/live-assets', icon: '🏦', label: '交易所账户' },
      ]
    },
    {
      title: '配置管理',
      items: [
        { path: '/strategies', icon: '🎯', label: '策略管理' },
        { path: '/exchanges', icon: '🔗', label: '交易所管理' },
        { path: '/exchange-pairs', icon: '🧩', label: '交易对管理' },
        { path: '/config-catalog', icon: '🗂️', label: '配置目录' },
        { path: '/risk', icon: '🛡️', label: '风险监控' },
        { path: '/settings', icon: '⚙️', label: '全局设置' },
      ]
    },
    {
      title: '用户管理',
      items: [
        { path: '/user', icon: '👤', label: '账户与密钥' },
      ]
    },
  ];

  return (
    <aside className="sidebar">
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
        {menuGroups.map((group, groupIndex) => (
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
    </aside>
  );
};

function App() {
  // 全局状态
  const [botStatus, setBotStatus] = useState('running');
  const [tradingMode, setTradingMode] = useState('paper');
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem('inarbit_user');
      if (raw) setCurrentUser(JSON.parse(raw));
    } catch {
      setCurrentUser(null);
    }
  }, []);

  const authed = !!getAuthToken();


  return (
    <Router>
      <div className="app-container">
        {/* 顶部灰绿色边条 */}
        <GlobalHeader botStatus={botStatus} />

        {/* 主体区域：侧边栏 + 内容 */}
        <div className="main-wrapper">
          <Sidebar botStatus={botStatus} tradingMode={tradingMode} currentUser={currentUser} />

          <main className="main-layout">
              <Routes>
                <Route path="/login" element={<Login onLogin={(u) => setCurrentUser(u)} />} />

                <Route path="/" element={
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
                <Route path="/oms" element={authed ? <OmsConsole /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/oms-config" element={authed ? <OmsConfig /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
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
                <Route path="/settings" element={authed ? <Settings /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
                <Route path="/risk" element={authed ? <RiskDashboard /> : <Login onLogin={(u) => setCurrentUser(u)} />} />
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
