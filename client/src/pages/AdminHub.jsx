import React from 'react';
import { Link } from 'react-router-dom';

const buildSections = (isAdmin) => ([
  {
    title: '系统与运行',
    items: [
      { label: '控制面板', path: '/control', desc: '启动/停止、模式切换与运行状态' },
      { label: '系统概览', path: '/system', desc: '核心服务健康与统计' },
      { label: '运行日志', path: '/logs', desc: '系统运行日志与审计线索' },
    ],
  },
  {
    title: '执行与调度',
    items: [
      { label: '机器人控制台', path: '/bot', desc: 'Bot 命令接口、持仓、手动下单与收益' },
      { label: '订单管理控制', path: '/oms', desc: '执行/对账/取消/收益与告警/参数' },
      ...(isAdmin ? [{ label: '扫描器参数', path: '/scanners', desc: 'Triangular/CashCarry 运行时调参（管理员）' }] : []),
      { label: '决策管理', path: '/decision', desc: '决策器输入/输出与阈值' },
      { label: '套利机会', path: '/arbitrage', desc: '机会发现与信号观测' },
    ],
  },
  {
    title: '市场与资产',
    items: [
      { label: '实时价格', path: '/live-prices', desc: '行情与市场快照' },
      { label: '收益展示', path: '/pnl', desc: '收益、费率与收益率' },
      { label: '模拟持仓', path: '/portfolio', desc: '模拟盘资产与持仓' },
      { label: '交易所账户', path: '/live-assets', desc: '实盘账户资产概览' },
    ],
  },
  {
    title: '交易所与策略',
    items: [
      { label: '交易所管理', path: '/exchanges', desc: '交易所接入与权限' },
      { label: '交易对管理', path: '/exchange-pairs', desc: '交易对启停与分配' },
      { label: '策略管理', path: '/strategies', desc: '策略启停、优先级与配置' },
      { label: '配置目录', path: '/config-catalog', desc: '系统配置项与说明' },
    ],
  },
  {
    title: '风险与权限',
    items: [
      ...(isAdmin ? [{ label: '风险监控', path: '/risk', desc: '风控阈值与告警（管理员）' }] : []),
      { label: '全局设置', path: '/settings', desc: '系统策略与风险配置' },
      { label: '模拟配置', path: '/sim-config', desc: '模拟盘参数与资金' },
      { label: '账户与密钥', path: '/user', desc: '账号信息与 API 密钥' },
    ],
  },
]);

const AdminHub = ({ currentUser }) => {
  const isAdmin = currentUser?.role === 'admin';
  const sections = buildSections(isAdmin);

  return (
    <div className="content-body">
    <div className="page-header" style={{ marginBottom: '16px' }}>
      <div>
        <h1 className="page-title">管理总览</h1>
        <p className="page-subtitle">统一入口与管理导航</p>
      </div>
    </div>

    <div style={{ display: 'grid', gap: '12px' }}>
      {sections.map((section) => (
        <div key={section.title} className="card">
          <div className="card-header"><span className="card-title">{section.title}</span></div>
          <div className="card-body" style={{ padding: '12px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '10px' }}>
              {section.items.map((item) => (
                <Link key={item.path} to={item.path} className="card" style={{ textDecoration: 'none' }}>
                  <div className="card-body" style={{ padding: '10px' }}>
                    <div style={{ fontWeight: 700, marginBottom: '6px', color: 'var(--text-primary)' }}>{item.label}</div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{item.desc}</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  </div>
  );
};

export default AdminHub;
