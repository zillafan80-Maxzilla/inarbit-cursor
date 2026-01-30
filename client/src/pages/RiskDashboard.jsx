/**
 * 风险监控仪表盘
 * 灰绿色主题重构版 - 分栏布局 + KPI仪表盘风格
 * 参考图3和图4设计
 */
import React, { useState, useEffect } from 'react';
import { riskAPI, systemAPI } from '../api/client';

const RiskDashboard = () => {
  const [tradingEnabled, setTradingEnabled] = useState(true);
  const [riskStatus, setRiskStatus] = useState({});
  const [systemMetrics, setSystemMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedMetric, setSelectedMetric] = useState(null);
  const metricsData = systemMetrics?.data ? systemMetrics.data : systemMetrics || {};
  const opportunities = metricsData?.opportunities || {};
  const decisionMetrics = metricsData?.decision_metrics || {};
  const omsMetrics = metricsData?.oms_metrics || {};
  const marketDataMetrics = metricsData?.market_data_metrics || {};
  const marketData = metricsData?.market_data || {};
  const health = metricsData?.health || {};

  const riskMetrics = {
    totalEquity: Number(riskStatus.total_equity || 0),
    drawdown: Number(riskStatus.drawdown || 0),
    exposure: Number(riskStatus.exposure || 0),
    panic: !!riskStatus.panic_triggered,
  };

  // KPI 指标配置 - 参考图3
  const kpiData = [
    {
      group: '收益指标',
      items: [
        {
          id: 'total_equity',
          label: '总权益',
          target: '目标：高于阈值',
          value: `$${riskMetrics.totalEquity.toLocaleString()}`,
          variance: 0,
          isPositive: riskMetrics.totalEquity >= 0,
          bars: [0.6, 0.62, 0.64, 0.63, 0.61, 0.65, 0.66, 0.67, 0.64, 0.62, 0.63, 0.66]
        },
        {
          id: 'max_drawdown',
          label: '最大回撤',
          target: '目标：小于 5%',
          value: `${riskMetrics.drawdown}%`,
          variance: riskMetrics.drawdown,
          isPositive: false,
          bars: [0.3, 0.4, 0.35, 0.5, 0.45, 0.6, 0.55, 0.4, 0.5, 0.45, 0.35, 0.4]
        },
        {
          id: 'panic',
          label: '紧急停止',
          target: '目标：未触发',
          value: riskMetrics.panic ? '触发' : '未触发',
          variance: 0,
          isPositive: !riskMetrics.panic,
          bars: [0.2, 0.2, 0.2, 0.3, 0.2, 0.25, 0.2, 0.3, 0.2, 0.2, 0.25, 0.2]
        },
      ]
    },
    {
      group: '风险指标',
      items: [
        {
          id: 'exposure',
          label: '总敞口',
          target: '目标：小于 10 万',
          value: `$${riskMetrics.exposure.toLocaleString()}`,
          variance: 0,
          isPositive: true,
          bars: [0.5, 0.55, 0.52, 0.6, 0.58, 0.55, 0.6, 0.58, 0.62, 0.6, 0.58, 0.55]
        },
      ]
    }
  ];

  const fetchStatus = async () => {
    try {
      const [res, metrics] = await Promise.all([
        riskAPI.status(),
        systemAPI.metrics(),
      ]);
      setTradingEnabled(!!res.trading_allowed);
      setRiskStatus(res.status || {});
      setSystemMetrics(metrics?.data || metrics || null);
    } catch (err) {
      console.error('获取风险状态失败:', err);
    } finally {
      setLoading(false);
    }
  };

  const triggerPanic = async () => {
    if (!confirm('⚠️ 确定要触发紧急停止吗？这将立即停止所有交易活动。')) return;
    try {
      await riskAPI.panic();
      await fetchStatus();
    } catch (err) {
      alert('触发失败: ' + err.message);
    }
  };

  const resetPanic = async () => {
    try {
      await riskAPI.resetPanic();
      await fetchStatus();
    } catch (err) {
      alert('重置失败: ' + err.message);
    }
  };

  const reloadKeys = async () => {
    try {
      await riskAPI.reloadKeys();
      alert('接口密钥已重载');
    } catch (err) {
      alert('重载失败: ' + err.message);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  useEffect(() => {
    if (!selectedMetric && kpiData.length > 0 && kpiData[0].items.length > 0) {
      setSelectedMetric(kpiData[0].items[0].id);
    }
  }, [selectedMetric, kpiData]);

  // 获取选中指标的详细信息
  const getSelectedMetricInfo = () => {
    if (!selectedMetric) return null;
    for (const group of kpiData) {
      const item = group.items.find(i => i.id === selectedMetric);
      if (item) return item;
    }
    return null;
  };

  const selectedInfo = getSelectedMetricInfo();

  if (loading) {
    return (
      <div className="loading">
        <div className="loading-spinner"></div>
      </div>
    );
  }

  return (
    <div className="content-body">
      {/* 页面标题 */}
      <div className="page-header">
        <div>
          <h1 className="page-title">风险监控</h1>
          <p className="page-subtitle">实时监控系统风险指标与交易状态</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={fetchStatus} className="btn btn-secondary">🔄 刷新</button>
          <button onClick={reloadKeys} className="btn btn-secondary">🔑 重载密钥</button>
        </div>
      </div>

      {/* 交易状态卡片 - 顶部 */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <div className="card-body" style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              fontSize: '24px',
              filter: tradingEnabled ? 'none' : 'grayscale(1)'
            }}>
              {tradingEnabled ? '🟢' : '🔴'}
            </div>
            <div>
              <div style={{
                fontSize: '14px',
                fontWeight: 700,
                color: tradingEnabled ? 'var(--color-success)' : 'var(--color-danger)'
              }}>
                {tradingEnabled ? '交易已启用' : '交易已暂停'}
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>
                {tradingEnabled ? '系统正在正常运行中' : '系统已触发紧急停止'}
              </div>
            </div>
          </div>
          <div>
            {tradingEnabled ? (
              <button onClick={triggerPanic} className="btn btn-danger">
                🛑 紧急停止
              </button>
            ) : (
              <button onClick={resetPanic} className="btn btn-primary">
                ✅ 恢复交易
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 分栏布局 - 参考图4 */}
      <div className="split-layout">
        {/* 左侧 - KPI 仪表盘列表（参考图3） */}
        <div className="split-layout-main">
          <div className="info-panel">
            <div className="info-panel-header">
              <div className="info-panel-title">
                <span>📊</span>
                <span>核心指标仪表盘</span>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <span className="table-badge success">● 达标</span>
                <span className="table-badge danger">● 未达标</span>
              </div>
            </div>
            <div className="info-panel-body">
              {kpiData.map((group, groupIndex) => (
                <div key={groupIndex}>
                  {/* 分组标题 */}
                  <div className="kpi-group-header">
                    <div className="kpi-group-title">{group.group}</div>
                  </div>

                  {/* KPI 行 */}
                  {group.items.map((item, itemIndex) => (
                    <div
                      key={itemIndex}
                      className="kpi-row"
                      onClick={() => setSelectedMetric(item.id)}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: selectedMetric === item.id ? 'var(--bg-active)' : 'transparent'
                      }}
                    >
                      {/* 标签 */}
                      <div className="kpi-row-label">
                        <div className="kpi-row-label-title">{item.label}</div>
                        <div className="kpi-row-label-target">{item.target}</div>
                      </div>

                      {/* 数值 */}
                      <div className="kpi-row-value">
                        <div className="kpi-row-num">{item.value}</div>
                        <div className={`kpi-row-variance ${item.variance >= 0 ? 'positive' : 'negative'}`}>
                          <span>{item.variance >= 0 ? '●' : '●'}</span>
                          <span>{item.variance >= 0 ? '+' : ''}{item.variance}%</span>
                          <span>偏差</span>
                        </div>
                      </div>

                      {/* 图表区域 */}
                      <div className="kpi-row-chart">
                        {/* 方差柱状图 */}
                        <div className="kpi-variance-bars">
                          {item.bars.map((height, barIndex) => (
                            <div
                              key={barIndex}
                              className={`kpi-variance-bar ${item.isPositive ? 'positive' : 'negative'}`}
                              style={{ height: `${height * 100}%` }}
                            />
                          ))}
                        </div>

                        {/* 趋势线占位 */}
                        <div className="kpi-trend-line" style={{
                          background: 'linear-gradient(90deg, transparent, var(--bg-main))',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'var(--text-muted)',
                          fontSize: '10px'
                        }}>
                          📈 趋势
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="info-panel" style={{ marginTop: '12px' }}>
            <div className="info-panel-header">
              <div className="info-panel-title">
                <span>📈</span>
                <span>系统指标</span>
              </div>
            </div>
            <div className="info-panel-body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px', marginBottom: '10px' }}>
                <div className="stat-box">
                  <div className="stat-label">机会池</div>
                  <div className="stat-num">{(opportunities.triangular || 0) + (opportunities.cashcarry || 0)}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>三角 {opportunities.triangular || 0} / 期现 {opportunities.cashcarry || 0}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">决策队列</div>
                  <div className="stat-num">{metricsData?.decisions || 0}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>过滤 {decisionMetrics?.blocked || 0} / 通过 {decisionMetrics?.passed || 0}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">OMS 执行</div>
                  <div className="stat-num">{omsMetrics?.executed || 0}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>失败 {omsMetrics?.failed || 0} / 拒单 {omsMetrics?.rejected || 0}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">行情健康</div>
                  <div className="stat-num" style={{ color: health?.market_data_fresh ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {health?.market_data_fresh ? '新鲜' : '滞后'}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                    延迟 {health?.market_data_age_ms ?? '-'} ms
                  </div>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px', marginBottom: '10px' }}>
                <div className="stat-box">
                  <div className="stat-label">行情覆盖</div>
                  <div className="stat-num">{marketData?.symbols_spot || 0}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>合约 {marketData?.symbols_futures || 0}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">盘口/费率</div>
                  <div className="stat-num">{marketData?.symbols_orderbook || 0}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>费率 {marketData?.symbols_funding || 0}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">决策延迟</div>
                  <div className="stat-num">{decisionMetrics?.latency_ms || 0} ms</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>窗口 {decisionMetrics?.window_size || 0}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">行情时间戳</div>
                  <div className="stat-num">{marketDataMetrics?.timestamp_ms || '-'}</div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>来源 {marketDataMetrics?.source || '-'}</div>
                </div>
              </div>
              <pre style={{ fontSize: '10px', whiteSpace: 'pre-wrap', marginTop: '8px' }}>
                {JSON.stringify(metricsData || {}, null, 2)}
              </pre>
            </div>
          </div>

          <div className="info-panel" style={{ marginTop: '12px' }}>
            <div className="info-panel-header">
              <div className="info-panel-title">
                <span>📌</span>
                <span>当前风险状态</span>
              </div>
            </div>
            <div className="info-panel-body">
              <pre style={{ fontSize: '10px', whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(riskStatus || {}, null, 2)}
              </pre>
            </div>
          </div>
        </div>

        {/* 右侧 - 配置面板（参考图4黄框） */}
        <div className="split-layout-aside">
          <div className="config-panel">
            <div className="config-panel-header">
              <div className="config-panel-title">
                {selectedInfo ? selectedInfo.label : '指标详情'}
              </div>
            </div>
            <div className="config-panel-body">
              {selectedInfo ? (
                <>
                  {/* 预览图表 */}
                  <div className="config-panel-preview" style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexDirection: 'column',
                    gap: '8px'
                  }}>
                    <div style={{
                      fontSize: '32px',
                      fontWeight: 700,
                      color: selectedInfo.isPositive ? 'var(--color-success)' : 'var(--color-danger)'
                    }}>
                      {selectedInfo.value}
                    </div>
                    <div style={{
                      fontSize: '12px',
                      color: 'var(--text-muted)'
                    }}>
                      {selectedInfo.target}
                    </div>
                  </div>

                  {/* 详细信息 */}
                  <div style={{ marginBottom: '16px' }}>
                    <div style={{
                      fontSize: '12px',
                      color: 'var(--text-muted)',
                      marginBottom: '8px'
                    }}>
                      状态说明
                    </div>
                    <p style={{
                      fontSize: '13px',
                      color: 'var(--text-secondary)',
                      lineHeight: 1.6,
                      margin: 0
                    }}>
                      当前 {selectedInfo.label}
                      {selectedInfo.isPositive ? ' 处于正常范围内，' : ' 需要关注，'}
                      较目标偏差 {selectedInfo.variance >= 0 ? '+' : ''}{selectedInfo.variance}%。
                      建议持续监控此指标变化趋势。
                    </p>
                  </div>

                  {/* 操作按钮 */}
                  <div className="config-panel-actions">
                    <button className="btn btn-secondary btn-sm">取消</button>
                    <button className="btn btn-primary btn-sm">查看详情</button>
                  </div>
                </>
              ) : (
                <div style={{
                  textAlign: 'center',
                  padding: '40px 20px',
                  color: 'var(--text-muted)'
                }}>
                  <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.5 }}>📊</div>
                  <p style={{ fontSize: '13px', margin: 0 }}>
                    点击左侧指标行<br />查看详细信息
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* 风险限制快捷卡片 */}
          <div className="config-panel" style={{ marginTop: '16px' }}>
            <div className="config-panel-header">
              <div className="config-panel-title">风险限制</div>
            </div>
            <div className="config-panel-body" style={{ padding: '12px 16px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>日最大亏损</span>
                  <span style={{ fontWeight: 600 }}>$0 / $5,000</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>单笔仓位</span>
                  <span style={{ fontWeight: 600 }}>$2,500 / $10,000</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>持仓数量</span>
                  <span style={{ fontWeight: 600 }}>12 / 50</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>日交易次数</span>
                  <span style={{ fontWeight: 600 }}>89 / 500</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskDashboard;
