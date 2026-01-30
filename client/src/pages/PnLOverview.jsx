/**
 * 收益展示页面
 * 重构版 - 根据交易模式显示对应收益曲线，交易明细增加交易所字段
 */
import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

import { useConnectedExchanges, useOmsPnLSummary, useOmsPnLHistory } from '../api/hooks';
import { createReconnectingWebSocketWithParams } from '../api/client';

const PnLOverview = ({ tradingMode = 'paper' }) => {
    const { exchanges, loading: exchangesLoading } = useConnectedExchanges();
    const [filters, setFilters] = useState({
        exchange_id: '',
        symbol: '',
        plan_id: '',
        created_after: '',
        created_before: '',
        limit: 200,
        offset: 0,
    });
    const [initialized, setInitialized] = useState(false);
    const [modeOverride, setModeOverride] = useState('');

    const effectiveMode = modeOverride || tradingMode;

    const historyParams = useMemo(() => ({
        trading_mode: effectiveMode,
        exchange_id: filters.exchange_id || undefined,
        symbol: filters.symbol || undefined,
        plan_id: filters.plan_id || undefined,
        created_after: filters.created_after || undefined,
        created_before: filters.created_before || undefined,
        limit: filters.limit,
        offset: filters.offset,
    }), [effectiveMode, filters]);

    const { summary: summaryBase, loading: summaryLoading } = useOmsPnLSummary({ trading_mode: effectiveMode });
    const { history: historyBase, loading: historyLoading } = useOmsPnLHistory(historyParams);
    const [liveSummary, setLiveSummary] = useState(null);
    const [liveHistory, setLiveHistory] = useState(null);
    const [streamActive, setStreamActive] = useState(false);

    useEffect(() => {
        if (initialized) return;
        const params = new URLSearchParams(window.location.search || '');
        const next = {
            exchange_id: params.get('exchange_id') || '',
            symbol: params.get('symbol') || '',
            plan_id: params.get('plan_id') || '',
            created_after: params.get('created_after') || '',
            created_before: params.get('created_before') || '',
            limit: Number(params.get('limit') || 200),
            offset: Number(params.get('offset') || 0),
        };
        const urlMode = params.get('trading_mode');
        if (urlMode === 'paper' || urlMode === 'live') {
            setModeOverride(urlMode);
        }
        setFilters((prev) => ({ ...prev, ...next }));
        setInitialized(true);
    }, [initialized]);

    useEffect(() => {
        const socket = createReconnectingWebSocketWithParams(
            'pnl',
            {
                trading_mode: effectiveMode,
                exchange_id: filters.exchange_id || '',
                symbol: filters.symbol || '',
                plan_id: filters.plan_id || '',
                created_after: filters.created_after || '',
                created_before: filters.created_before || '',
                limit: String(filters.limit || 200),
                offset: String(filters.offset || 0),
                interval: '1',
            },
            (payload) => {
                if (!payload || payload.type !== 'pnl') return;
                setLiveSummary(payload.summary || null);
                setLiveHistory(Array.isArray(payload.history) ? payload.history : []);
                setStreamActive(true);
            },
            3000
        );
        return () => socket.close();
    }, [
        effectiveMode,
        filters.exchange_id,
        filters.symbol,
        filters.plan_id,
        filters.created_after,
        filters.created_before,
        filters.limit,
        filters.offset,
    ]);

    const isPaper = effectiveMode === 'paper';
    const lineColor = isPaper ? 'var(--cyan)' : 'var(--color-danger)';
    const modeName = isPaper ? '模拟盘' : '实盘';

    const summary = liveSummary ?? summaryBase;
    const history = liveHistory ?? historyBase;
    const pnlHistory = Array.isArray(history) ? history : [];
    const stats = summary || {};

    const parseRowDate = (row) => {
        const raw = row?.created_at || row?.exit_time || row?.entry_time;
        if (!raw) return null;
        const d1 = new Date(raw);
        if (!Number.isNaN(d1.getTime())) return d1;
        const trimmed = String(raw).replace(/(\.\d{3})\d+/, '$1');
        const d2 = new Date(trimmed);
        return Number.isNaN(d2.getTime()) ? null : d2;
    };

    const chartData = useMemo(() => {
        if (!pnlHistory.length) return [];
        const daily = new Map();
        pnlHistory.forEach((row) => {
            const date = parseRowDate(row) || new Date();
            const key = date.toISOString().slice(0, 10);
            const profit = Number(row.profit || 0);
            daily.set(key, (daily.get(key) || 0) + profit);
        });
        const days = Array.from(daily.entries())
            .sort((a, b) => a[0].localeCompare(b[0]));
        let acc = 0;
        return days.map(([day, value]) => {
            acc += value;
            return { date: day.slice(5), value: Number(acc.toFixed(6)) };
        });
    }, [pnlHistory]);

    const pagedTrades = useMemo(() => {
        const rows = [...pnlHistory];
        rows.sort((a, b) => {
            const ad = parseRowDate(a)?.getTime() || 0;
            const bd = parseRowDate(b)?.getTime() || 0;
            return bd - ad;
        });
        return rows;
    }, [pnlHistory]);

    const exchangeBreakdown = useMemo(() => {
        const map = new Map();
        pnlHistory.forEach((row) => {
            const key = row.exchange_id || 'unknown';
            const profit = Number(row.profit || 0);
            map.set(key, (map.get(key) || 0) + profit);
        });
        return Array.from(map.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, 6);
    }, [pnlHistory]);

    const symbolBreakdown = useMemo(() => {
        const map = new Map();
        pnlHistory.forEach((row) => {
            const key = row.symbol || '未知';
            const profit = Number(row.profit || 0);
            map.set(key, (map.get(key) || 0) + profit);
        });
        return Array.from(map.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8);
    }, [pnlHistory]);

    const totalProfit = Number(stats.total_profit || 0);
    const totalOrders = Number(stats.total_orders || pnlHistory.length || 0);
    const avgProfit = Number(stats.avg_profit || 0);
    const winRate = Number(stats.win_rate || (totalOrders ? (pnlHistory.filter((r) => Number(r.profit || 0) > 0).length / totalOrders) : 0));

    const todayKey = new Date().toISOString().slice(0, 10);
    const todayRows = pnlHistory.filter((row) => {
        const d = parseRowDate(row);
        if (!d) return false;
        const day = d.toISOString().slice(0, 10);
        return day === todayKey;
    });
    const todayCount = todayRows.length;
    const todayWinRate = todayCount ? (todayRows.filter((r) => Number(r.profit || 0) > 0).length / todayCount) : 0;

    const formatProfit = (value) => {
        const num = Number(value || 0);
        return `${num >= 0 ? '+' : ''}${num.toFixed(4)} USDT`;
    };

    const formatRate = (value) => {
        if (value === null || value === undefined) return '—';
        const num = Number(value);
        if (Number.isNaN(num)) return '—';
        const pct = Math.abs(num) <= 1 ? num * 100 : num;
        return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
    };

    const exportJson = () => {
        const payload = JSON.stringify(pnlHistory, null, 2);
        const blob = new Blob([payload], { type: 'application/json;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `收益记录_${modeName}_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const exportCsv = () => {
        const header = ['时间', '交易所', '交易对', '收益', '收益率', '数量'];
        const rows = pnlHistory.map((trade) => {
            const time = new Date(trade.created_at || trade.exit_time || trade.entry_time || Date.now()).toISOString();
            return [
                time,
                trade.exchange_id || '',
                trade.symbol || '',
                trade.profit || 0,
                trade.profit_rate || '',
                trade.quantity || '',
            ];
        });
        const content = [header, ...rows]
            .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
            .join('\n');
        const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `收益记录_${modeName}_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    if (exchangesLoading || summaryLoading || historyLoading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载交易所配置...</p>
            </div>
        );
    }

    if (!(exchanges || []).length) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>ℹ️</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无已连接交易所，请先在“交易所管理”中添加并连接。</p>
            </div>
        );
    }

    return (
        <div className="content-body">
            {/* 页面标题 */}
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">收益展示</h1>
                    <p className="page-subtitle">{modeName}收益数据与交易明细</p>
                </div>
            </div>

            {/* 当前模式收益卡片 */}
            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">{modeName}累计收益</div>
                    <div className="stat-num highlight">{formatProfit(totalProfit)}</div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        平均单笔收益: {formatProfit(avgProfit)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">今日套利次数</div>
                    <div className="stat-num">{todayCount}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">今日胜率</div>
                    <div className="stat-num">{(todayWinRate * 100).toFixed(2)}%</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">累计胜率</div>
                    <div className="stat-num">{(winRate * 100).toFixed(2)}%</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">当前模式</div>
                    <div className="stat-num" style={{ color: lineColor, fontSize: '13px' }}>
                        {isPaper ? '📝 模拟' : '💰 实盘'}
                    </div>
                </div>
            </div>

            {/* 收益曲线 */}
            <div className="stat-box" style={{ height: '260px', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 500 }}>
                    {modeName}收益曲线
                </h3>
                <ResponsiveContainer width="100%" height="90%">
                    <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                        <XAxis dataKey="date" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                        <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                        <Tooltip
                            contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }}
                        />
                        <Line
                            type="monotone"
                            dataKey="value"
                            name={modeName}
                            stroke={lineColor}
                            strokeWidth={2}
                            dot={{ r: 2 }}
                        />
                    </LineChart>
                </ResponsiveContainer>
                {!chartData.length && (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px', marginTop: '8px' }}>
                        暂无收益曲线数据
                    </div>
                )}
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">累计成交数</div>
                    <div className="stat-num">{totalOrders}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">累计胜率</div>
                    <div className="stat-num">{(winRate * 100).toFixed(2)}%</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">累计收益</div>
                    <div className="stat-num" style={{ color: totalProfit >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                        {formatProfit(totalProfit)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">平均收益</div>
                    <div className="stat-num">{formatProfit(avgProfit)}</div>
                </div>
            </div>

            <div className="card" style={{ marginBottom: '16px' }}>
                <div className="card-header"><span className="card-title">🔎 收益筛选</span></div>
                <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: '10px' }}>
                    <div>
                        <label className="form-label">交易所</label>
                        <select className="form-input" value={filters.exchange_id} onChange={(e) => setFilters((prev) => ({ ...prev, exchange_id: e.target.value, offset: 0 }))}>
                            <option value="">全部</option>
                            {(exchanges || []).map((ex) => (
                                <option key={ex.id || ex.exchange_id || ex.name} value={ex.exchange_id || ex.id || ex.name}>{ex.name || ex.exchange_id || ex.id}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="form-label">交易对</label>
                        <input className="form-input" placeholder="如 BTC/USDT" value={filters.symbol} onChange={(e) => setFilters((prev) => ({ ...prev, symbol: e.target.value, offset: 0 }))} />
                    </div>
                    <div>
                        <label className="form-label">计划编号</label>
                        <input className="form-input" placeholder="计划编号" value={filters.plan_id} onChange={(e) => setFilters((prev) => ({ ...prev, plan_id: e.target.value, offset: 0 }))} />
                    </div>
                    <div>
                        <label className="form-label">开始时间</label>
                        <input className="form-input" type="datetime-local" value={filters.created_after} onChange={(e) => setFilters((prev) => ({ ...prev, created_after: e.target.value, offset: 0 }))} />
                    </div>
                    <div>
                        <label className="form-label">结束时间</label>
                        <input className="form-input" type="datetime-local" value={filters.created_before} onChange={(e) => setFilters((prev) => ({ ...prev, created_before: e.target.value, offset: 0 }))} />
                    </div>
                    <div>
                        <label className="form-label">每页数量</label>
                        <input className="form-input" type="number" min={50} max={500} value={filters.limit} onChange={(e) => setFilters((prev) => ({ ...prev, limit: Number(e.target.value || 200), offset: 0 }))} />
                    </div>
                    <div className="pnl-filter-actions" style={{ gridColumn: '1 / -1', alignItems: 'flex-end', gap: '8px' }}>
                        <button className="btn" onClick={() => setFilters((prev) => ({ ...prev, offset: Math.max(prev.offset - prev.limit, 0) }))}>上一页</button>
                        <button className="btn" onClick={() => setFilters((prev) => ({ ...prev, offset: prev.offset + prev.limit }))}>下一页</button>
                        <button className="btn" onClick={() => {
                            const dt = new Date();
                            dt.setDate(dt.getDate() - 7);
                            setFilters((prev) => ({ ...prev, created_after: dt.toISOString().slice(0, 16), offset: 0 }));
                        }}>近7天</button>
                        <button className="btn" onClick={() => {
                            const dt = new Date();
                            dt.setDate(dt.getDate() - 30);
                            setFilters((prev) => ({ ...prev, created_after: dt.toISOString().slice(0, 16), offset: 0 }));
                        }}>近30天</button>
                        <button className="btn btn-outline" onClick={() => setFilters({ exchange_id: '', symbol: '', plan_id: '', created_after: '', created_before: '', limit: 200, offset: 0 })}>重置</button>
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">交易所收益前列</div>
                    <div style={{ marginTop: '8px' }}>
                        {exchangeBreakdown.length ? exchangeBreakdown.map(([name, profit]) => (
                            <div key={name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', marginBottom: '4px' }}>
                                <span>{name}</span>
                                <span style={{ color: profit >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>{formatProfit(profit)}</span>
                            </div>
                        )) : (
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>暂无数据</div>
                        )}
                    </div>
                </div>
                <div className="stat-box" style={{ gridColumn: 'span 3' }}>
                    <div className="stat-label">交易对收益前列</div>
                    <div style={{ marginTop: '8px', display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '8px' }}>
                        {symbolBreakdown.length ? symbolBreakdown.map(([name, profit]) => (
                            <div key={name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px' }}>
                                <span>{name}</span>
                                <span style={{ color: profit >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>{formatProfit(profit)}</span>
                            </div>
                        )) : (
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>暂无数据</div>
                        )}
                    </div>
                </div>
            </div>

            {/* 交易明细 - 增加交易所字段 */}
            <div className="stat-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <h3 style={{ fontSize: '11px', fontWeight: 500 }}>最近收益明细</h3>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <button className="btn" onClick={exportCsv}>导出表格</button>
                        <button className="btn btn-outline" onClick={exportJson}>导出数据</button>
                    </div>
                </div>
                <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                    当前页: {Math.floor(filters.offset / filters.limit) + 1} · 每页 {filters.limit} 条
                </div>
                <div className="data-table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>交易所</th>
                                <th>路径</th>
                                <th>收益率</th>
                                <th>收益</th>
                                <th>数量</th>
                            </tr>
                        </thead>
                        <tbody>
                            {pagedTrades.map((trade) => {
                                const tradeTime = new Date(trade.created_at || trade.exit_time || trade.entry_time || Date.now());
                                const displayTime = tradeTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                                const exchangeLabel = trade.exchange_id || 'unknown';
                                const pathLabel = trade.symbol || '—';
                                const profitRate = trade.profit_rate;
                                const profitText = formatProfit(trade.profit);
                                const profitColor = Number(trade.profit || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)';

                                return (
                                    <tr key={trade.id || `${trade.created_at}-${trade.symbol}`}> 
                                        <td style={{ fontSize: '10px' }}>{displayTime}</td>
                                        <td>
                                            <span style={{
                                                fontSize: '9px',
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                background: 'rgba(42, 161, 152, 0.1)',
                                                color: '#2aa198'
                                            }}>
                                                {exchangeLabel}
                                            </span>
                                        </td>
                                        <td style={{ fontSize: '10px', fontFamily: 'monospace' }}>{pathLabel}</td>
                                        <td style={{ color: profitColor, fontSize: '10px' }}>{formatRate(profitRate)}</td>
                                        <td style={{ fontSize: '10px' }}>{profitText}</td>
                                        <td style={{ fontSize: '10px' }}>{trade.quantity ?? '—'}</td>
                                    </tr>
                                );
                            })}
                            {!pagedTrades.length && (
                                <tr>
                                    <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>
                                        暂无收益明细
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default PnLOverview;
