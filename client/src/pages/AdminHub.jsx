import React from 'react';
import { Link } from 'react-router-dom';

const buildSections = (isAdmin) => ([
  {
    title: '系统与运行',
    items: [
      { label: '收益总览', path: '/realtime', desc: '资金收益与核心状态（统一口径）' },
      { label: '控制面板', path: '/control', desc: '启停/模式/策略/持仓/手动下单' },
      { label: '系统概览', path: '/system', desc: '核心服务健康与统计' },
      { label: '运行日志', path: '/logs', desc: '系统运行日志与审计线索' },
    ],
  },
  {
    title: '执行与调度',
    items: [
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
      { label: '交易所账户', path: '/live-assets', desc: '实盘账户资产概览' },
      { label: '模拟持仓', path: '/portfolio', desc: '模拟盘资产与持仓（权益拆分）' },
      { label: '收益展示', path: '/pnl', desc: '收益曲线、交易明细与费率' },
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
    <div className="page-header" style={{ marginBottom: '10px' }}>
      <div>
        <h1 className="page-title">管理总览</h1>
        <p className="page-subtitle">统一入口与管理导航（紧凑布局）</p>
      </div>
    </div>

    <div style={{ display: 'grid', gap: '8px' }}>
      {sections.map((section) => (
        <div key={section.title} className="card">
          <div className="card-header" style={{ padding: '6px 10px' }}>
            <span className="card-title" style={{ fontSize: '11px', lineHeight: 1.1 }}>{section.title}</span>
          </div>
          <div className="card-body" style={{ padding: '8px' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))',
                gap: '6px',
              }}
            >
              {section.items.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className="card"
                  style={{
                    textDecoration: 'none',
                    display: 'flex',
                    alignItems: 'stretch',
                  }}
                >
                  <div
                    className="card-body"
                    style={{
                      padding: '6px 8px',
                      width: '100%',
                      minHeight: '44px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'center',
                      gap: '3px',
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: '10px', lineHeight: 1.1, color: 'var(--text-primary)' }}>
                      {item.label}
                    </div>
                    <div
                      style={{
                        fontSize: '8px',
                        color: 'var(--text-muted)',
                        lineHeight: 1.1,
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}
                    >
                      {item.desc}
                    </div>
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
