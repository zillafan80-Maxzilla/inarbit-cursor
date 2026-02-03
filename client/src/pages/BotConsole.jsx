import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { botAPI } from '../api/client';

function safeJsonParse(text) {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

const BotConsole = () => {
  const [status, setStatus] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [positions, setPositions] = useState([]);
  const [pnlSummary, setPnlSummary] = useState(null);
  const [pnlDaily, setPnlDaily] = useState([]);
  const [days, setDays] = useState(7);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [activeTab, setActiveTab] = useState('status'); // status | strategies | positions | manual | pnl

  const [strategyDrafts, setStrategyDrafts] = useState({});
  const [strategySaving, setStrategySaving] = useState({});
  const [strategyToggling, setStrategyToggling] = useState({});

  const [manual, setManual] = useState({
    symbol: 'BTC/USDT',
    side: 'buy',
    order_type: 'market',
    amount: 0.001,
    price: '',
  });
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [manualResult, setManualResult] = useState(null);

  const isRunning = (status?.data?.status || status?.status) === 'running';
  const tradingMode = status?.data?.trading_mode || status?.data?.tradingMode || status?.trading_mode || '-';
  const startTs = status?.data?.start_timestamp || null;

  const uptimeText = useMemo(() => {
    if (!isRunning || !startTs) return '00:00:00';
    const elapsed = Math.max(0, Date.now() - Number(startTs) * 1000);
    const hours = Math.floor(elapsed / 3600000);
    const minutes = Math.floor((elapsed % 3600000) / 60000);
    const seconds = Math.floor((elapsed % 60000) / 1000);
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }, [isRunning, startTs, Math.floor(Date.now() / 1000)]);

  const loadAll = async () => {
    setLoading(true);
    setError('');
    try {
      const [s, st, p, ps] = await Promise.all([
        botAPI.status(),
        botAPI.listStrategies(),
        botAPI.positions(),
        botAPI.pnlSummary(),
      ]);
      setStatus(s || null);
      setStrategies(st?.data || []);
      setPositions(p?.data || []);
      setPnlSummary(ps?.data || ps || null);
      setManualResult(null);

      const d = await botAPI.pnlDaily(days);
      setPnlDaily(d?.data || []);

      const nextDrafts = {};
      (st?.data || []).forEach((item) => {
        const cfg = item.config;
        let raw = '{}';
        if (typeof cfg === 'string') raw = cfg;
        else raw = JSON.stringify(cfg || {}, null, 2);
        nextDrafts[item.id] = raw;
      });
      setStrategyDrafts(nextDrafts);
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeTab !== 'pnl') return;
    botAPI.pnlDaily(days)
      .then((resp) => setPnlDaily(resp?.data || []))
      .catch(() => {});
  }, [activeTab, days]);

  const start = async () => {
    try {
      await botAPI.start();
      await loadAll();
    } catch (e) {
      alert(String(e?.message || e));
    }
  };

  const stop = async () => {
    try {
      await botAPI.stop();
      await loadAll();
    } catch (e) {
      alert(String(e?.message || e));
    }
  };

  const restart = async () => {
    if (!confirm('确认重启机器人？')) return;
    try {
      await botAPI.restart();
      await loadAll();
    } catch (e) {
      alert(String(e?.message || e));
    }
  };

  const toggleStrategy = async (id, targetEnabled) => {
    setStrategyToggling((prev) => ({ ...prev, [id]: true }));
    try {
      await botAPI.toggleStrategy(id, targetEnabled);
      await loadAll();
    } catch (e) {
      alert(String(e?.message || e));
    }
    setStrategyToggling((prev) => ({ ...prev, [id]: false }));
  };

  const saveStrategyConfig = async (id) => {
    const raw = strategyDrafts[id] || '{}';
    const parsed = safeJsonParse(raw);
    if (!parsed.ok) {
      alert(`JSON 解析失败：${parsed.error}`);
      return;
    }
    setStrategySaving((prev) => ({ ...prev, [id]: true }));
    try {
      await botAPI.updateStrategyConfig(id, parsed.value);
      await loadAll();
      alert('策略配置已更新');
    } catch (e) {
      alert(String(e?.message || e));
    }
    setStrategySaving((prev) => ({ ...prev, [id]: false }));
  };

  const submitManual = async () => {
    if (!confirm('确认提交手动下单？仅模拟盘允许。')) return;
    setManualSubmitting(true);
    setManualResult(null);
    try {
      const payload = {
        symbol: manual.symbol,
        side: manual.side,
        amount: Number(manual.amount),
        order_type: manual.order_type,
        price: manual.order_type === 'limit' ? (manual.price === '' ? null : Number(manual.price)) : null,
      };
      const resp = await botAPI.manualOrder(payload);
      setManualResult(resp);
      await loadAll();
    } catch (e) {
      alert(String(e?.message || e));
    }
    setManualSubmitting(false);
  };

  return (
    <div className="content-body">
      <div className="page-header" style={{ marginBottom: '16px' }}>
        <div>
          <h1 className="page-title">机器人控制台</h1>
          <p className="page-subtitle">Bot 命令接口、策略开关、持仓与手动下单（模拟盘）</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={loadAll} className="btn btn-secondary">🔄 刷新</button>
          <button onClick={restart} className="btn btn-secondary" disabled={!isRunning}>🔄 重启</button>
          {isRunning ? (
            <button onClick={stop} className="btn btn-danger">🛑 停止</button>
          ) : (
            <button onClick={start} className="btn btn-primary">▶️ 启动</button>
          )}
        </div>
      </div>

      {loading && (
        <div className="loading">
          <div className="loading-spinner"></div>
        </div>
      )}

      {!loading && error && (
        <div className="stat-box" style={{ padding: '12px', color: 'var(--color-danger)' }}>{error}</div>
      )}

      {!loading && !error && (
        <>
          <div className="stats-row" style={{ marginBottom: '12px' }}>
            <div className="stat-box">
              <div className="stat-label">状态</div>
              <div className="stat-num" style={{ color: isRunning ? 'var(--color-success)' : 'var(--color-danger)' }}>
                {isRunning ? '运行中' : '已停止'}
              </div>
            </div>
            <div className="stat-box">
              <div className="stat-label">交易模式</div>
              <div className="stat-num">{tradingMode === 'live' ? '🔴 实盘' : '🟢 模拟'}</div>
            </div>
            <div className="stat-box">
              <div className="stat-label">运行时间</div>
              <div className="stat-num" style={{ fontFamily: 'monospace' }}>{uptimeText}</div>
            </div>
            <div className="stat-box">
              <div className="stat-label">启用策略数</div>
              <div className="stat-num">{status?.data?.active_strategies ?? '-'}</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
            {[
              { id: 'status', label: '概览', icon: '📌' },
              { id: 'strategies', label: '策略', icon: '🎯' },
              { id: 'positions', label: '持仓', icon: '📦' },
              { id: 'manual', label: '手动下单', icon: '📝' },
              { id: 'pnl', label: '收益', icon: '💰' },
            ].map((t) => (
              <button
                key={t.id}
                className={`btn btn-sm ${activeTab === t.id ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.icon} {t.label}
              </button>
            ))}
            <div style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>详细策略编辑请到</span>
              <Link to="/strategies" style={{ color: 'var(--cyan)', textDecoration: 'none', fontWeight: 700 }}>策略管理</Link>
            </div>
          </div>

          {activeTab === 'status' && (
            <div className="stat-box" style={{ padding: '12px' }}>
              <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>Bot 状态原始数据</h3>
              <pre style={{ fontSize: '10px', whiteSpace: 'pre-wrap', maxHeight: '360px', overflow: 'auto', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px' }}>
                {JSON.stringify(status || {}, null, 2)}
              </pre>
            </div>
          )}

          {activeTab === 'strategies' && (
            <div className="stat-box" style={{ padding: '12px' }}>
              <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>策略列表（Bot Control）</h3>
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>类型</th>
                      <th>优先级</th>
                      <th>状态</th>
                      <th style={{ width: '220px' }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategies.map((s) => (
                      <tr key={s.id}>
                        <td>{s.name}</td>
                        <td style={{ fontFamily: 'monospace' }}>{s.strategy_type}</td>
                        <td>{s.priority}</td>
                        <td>
                          <span className={`table-badge ${s.is_enabled ? 'success' : 'neutral'}`}>
                            {s.is_enabled ? '● 启用' : '○ 禁用'}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                            <button
                              className={`btn btn-sm ${s.is_enabled ? 'btn-danger' : 'btn-primary'}`}
                              disabled={!!strategyToggling[s.id]}
                              onClick={() => toggleStrategy(s.id, !s.is_enabled)}
                            >
                              {strategyToggling[s.id] ? '处理中...' : (s.is_enabled ? '禁用' : '启用')}
                            </button>
                            <button
                              className="btn btn-sm btn-secondary"
                              disabled={!!strategySaving[s.id]}
                              onClick={() => saveStrategyConfig(s.id)}
                            >
                              {strategySaving[s.id] ? '保存中...' : '保存配置'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {strategies.length === 0 && (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>暂无策略</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div style={{ marginTop: '12px', display: 'grid', gap: '12px' }}>
                {strategies.slice(0, 6).map((s) => (
                  <div key={`${s.id}-cfg`} style={{ border: '1px solid rgba(0,0,0,0.06)', borderRadius: '8px', padding: '10px', background: 'rgba(0,0,0,0.01)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700 }}>
                        {s.name} <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>({s.strategy_type})</span>
                      </div>
                      <button className="btn btn-sm btn-secondary" onClick={() => saveStrategyConfig(s.id)} disabled={!!strategySaving[s.id]}>
                        {strategySaving[s.id] ? '保存中...' : '保存'}
                      </button>
                    </div>
                    <textarea
                      value={strategyDrafts[s.id] || '{}'}
                      onChange={(e) => setStrategyDrafts((prev) => ({ ...prev, [s.id]: e.target.value }))}
                      style={{
                        marginTop: '8px',
                        width: '100%',
                        minHeight: '140px',
                        fontSize: '10px',
                        fontFamily: 'monospace',
                        borderRadius: '6px',
                        border: '1px solid rgba(0,0,0,0.08)',
                        padding: '8px',
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'positions' && (
            <div className="stat-box" style={{ padding: '12px' }}>
              <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>当前持仓（Bot Control）</h3>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                包含 paper_positions + short_leverage Redis 持仓汇总。
              </div>
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>来源</th>
                      <th>交易所</th>
                      <th>账户类型</th>
                      <th>品种</th>
                      <th>数量</th>
                      <th>均价</th>
                      <th>更新时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p, idx) => (
                      <tr key={`${idx}-${p.id || p.symbol || p.instrument || ''}`}>
                        <td style={{ fontFamily: 'monospace' }}>{p.type}</td>
                        <td>{p.exchange_id || p.exchange || '-'}</td>
                        <td>{p.account_type || '-'}</td>
                        <td style={{ fontFamily: 'monospace' }}>{p.instrument || p.symbol || '-'}</td>
                        <td style={{ fontFamily: 'monospace' }}>{p.quantity ?? p.qty ?? '-'}</td>
                        <td style={{ fontFamily: 'monospace' }}>{p.avg_price ?? p.entry_price ?? '-'}</td>
                        <td style={{ fontFamily: 'monospace' }}>{p.updated_at || p.updatedAt || '-'}</td>
                      </tr>
                    ))}
                    {positions.length === 0 && (
                      <tr>
                        <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>暂无持仓</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <pre style={{ fontSize: '10px', marginTop: '12px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '260px', overflow: 'auto' }}>
                {JSON.stringify(positions.slice(0, 20), null, 2)}
              </pre>
            </div>
          )}

          {activeTab === 'manual' && (
            <div className="stat-box" style={{ padding: '12px' }}>
              <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>手动下单（仅模拟盘）</h3>
              <div style={{ marginBottom: '10px', padding: '10px', background: 'rgba(220, 50, 47, 0.06)', borderRadius: '8px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                注意：该接口在后端强制要求 `trading_mode=paper`，并会写入 `order_history`（用于测试/演示）。
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '10px' }}>
                <div>
                  <label className="form-label">交易对</label>
                  <input className="form-input" value={manual.symbol} onChange={(e) => setManual((p) => ({ ...p, symbol: e.target.value }))} />
                </div>
                <div>
                  <label className="form-label">方向</label>
                  <select className="form-input" value={manual.side} onChange={(e) => setManual((p) => ({ ...p, side: e.target.value }))}>
                    <option value="buy">买入</option>
                    <option value="sell">卖出</option>
                  </select>
                </div>
                <div>
                  <label className="form-label">类型</label>
                  <select className="form-input" value={manual.order_type} onChange={(e) => setManual((p) => ({ ...p, order_type: e.target.value }))}>
                    <option value="market">市价</option>
                    <option value="limit">限价</option>
                  </select>
                </div>
                <div>
                  <label className="form-label">数量</label>
                  <input className="form-input" type="number" step="0.000001" value={manual.amount} onChange={(e) => setManual((p) => ({ ...p, amount: e.target.value }))} />
                </div>
                <div>
                  <label className="form-label">价格（限价）</label>
                  <input className="form-input" type="number" step="0.01" value={manual.price} onChange={(e) => setManual((p) => ({ ...p, price: e.target.value }))} disabled={manual.order_type !== 'limit'} />
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button className="btn btn-primary" onClick={submitManual} disabled={manualSubmitting}>
                  {manualSubmitting ? '提交中...' : '提交下单'}
                </button>
              </div>

              {manualResult && (
                <pre style={{ fontSize: '10px', marginTop: '12px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '260px', overflow: 'auto' }}>
                  {JSON.stringify(manualResult, null, 2)}
                </pre>
              )}
            </div>
          )}

          {activeTab === 'pnl' && (
            <div className="stat-box" style={{ padding: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
                <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>收益（Bot Control）</h3>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>天数</span>
                  <input
                    className="form-input"
                    style={{ width: '90px', height: '28px' }}
                    type="number"
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                  />
                </div>
              </div>

              <div className="stats-row" style={{ marginBottom: '12px' }}>
                <div className="stat-box">
                  <div className="stat-label">初始资金</div>
                  <div className="stat-num">{Number(pnlSummary?.initial_balance || 0).toFixed(2)} {pnlSummary?.currency || 'USDT'}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">当前资金</div>
                  <div className="stat-num">{Number(pnlSummary?.current_balance || 0).toFixed(2)} {pnlSummary?.currency || 'USDT'}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">净利润</div>
                  <div className="stat-num" style={{ color: Number(pnlSummary?.net_profit || 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
                    {Number(pnlSummary?.net_profit || 0).toFixed(4)}
                  </div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">收益率</div>
                  <div className="stat-num">{Number(pnlSummary?.profit_rate || 0).toFixed(3)}%</div>
                </div>
              </div>

              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>收益</th>
                      <th>交易次数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pnlDaily.map((row, idx) => (
                      <tr key={`${row.date || idx}`}>
                        <td style={{ fontFamily: 'monospace' }}>{row.date}</td>
                        <td style={{ fontFamily: 'monospace' }}>{Number(row.total_profit || 0).toFixed(6)}</td>
                        <td>{row.trade_count}</td>
                      </tr>
                    ))}
                    {pnlDaily.length === 0 && (
                      <tr>
                        <td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>暂无数据</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default BotConsole;

