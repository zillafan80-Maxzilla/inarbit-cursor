import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { systemAPI } from '../api/client';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const fetchAPI = async (path) => {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('auth_token') || ''}`,
      'Content-Type': 'application/json'
    }
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
};

const formatUptime = (totalSeconds) => {
    const safeSeconds = Math.max(0, Number(totalSeconds || 0));
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = Math.floor(safeSeconds % 60);
    return `${hours}小时${minutes}分钟${seconds}秒`;
};

const formatMoney = (value, currency = 'USDT') => {
    const num = Number(value || 0);
    return `${currency}$${num.toFixed(2)}`;
};

const RealtimeOverview = () => {
    const [payload, setPayload] = useState(null);
    const [stats, setStats] = useState(null);
    const [trades, setTrades] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [tick, setTick] = useState(Date.now());

    // 每秒更新时钟
    useEffect(() => {
        const timer = setInterval(() => setTick(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);

    // 加载系统总览数据
    useEffect(() => {
        let active = true;
        const load = async () => {
            try {
                const res = await systemAPI.realtime(false);
                if (!active) return;
                const data = res?.data || res || {};
                setPayload(data);
                setError(null);
            } catch (e) {
                if (!active) return;
                setError(e.message || '加载失败');
            } finally {
                if (active) setLoading(false);
            }
        };

        load();
        const interval = setInterval(load, 5000);
        return () => {
            active = false;
            clearInterval(interval);
        };
    }, []);

    // 加载运行统计数据
    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await fetchAPI('/api/v1/stats/realtime');
                if (res.success) {
                    setStats(res.data);
                }
            } catch (error) {
                console.error('获取统计数据失败:', error);
            }
        };

        const fetchTrades = async () => {
            try {
                const res = await fetchAPI('/api/v1/stats/trades/recent?limit=20');
                if (res.success) {
                    setTrades(res.data);
                }
            } catch (error) {
                console.error('获取交易记录失败:', error);
            }
        };

        fetchStats();
        fetchTrades();
        
        const statsInterval = setInterval(fetchStats, 3000);
        const tradesInterval = setInterval(fetchTrades, 5000);

        return () => {
            clearInterval(statsInterval);
            clearInterval(tradesInterval);
        };
    }, []);

    const summary = payload?.summary || {};
    const currentTime = new Date(tick);
    
    // 优先使用stats数据，回退到summary数据
    const runtime = stats?.runtime || { hours: 0, minutes: 0, seconds: 0 };
    const tradingMode = stats?.trading_mode || summary.trading_mode || '无';
    const initialBalance = stats?.initial_balance || Number(summary.initial_capital || 0);
    const currentBalance = stats?.current_balance || Number(summary.current_balance || 0);
    const netProfit = stats?.net_profit || Number(summary.net_profit || 0);
    const activeStrategies = stats?.active_strategies?.filter(s => s && s !== '无') || summary.strategies || [];
    const activeExchanges = stats?.active_exchanges?.filter(e => e && e !== '无') || summary.exchanges || [];
    const tradingPairs = stats?.trading_pairs?.filter(p => p && p !== '无') || summary.pairs || [];

    // 收益曲线数据（优先使用stats，回退到payload）
    const profitHistory = stats?.profit_history || [];
    const profitCurve = Array.isArray(payload?.profit_curve) ? payload.profit_curve : [];
    const chartData = profitHistory.length > 0 
        ? profitHistory.map(item => ({
            time: new Date(item.timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
            balance: item.balance,
            profit: item.balance - initialBalance
          }))
        : profitCurve.map((pt) => {
            const ts = pt.timestamp ? new Date(pt.timestamp) : new Date();
            const label = ts.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            return { time: label, balance: Number(pt.value || 0), profit: Number(pt.value || 0) - initialBalance };
          });

    // 交易记录（优先使用trades，回退到payload）
    const tradeList = trades.length > 0 ? trades : (Array.isArray(payload?.trades) ? payload.trades : []);

    if (loading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载实时总览...</p>
            </div>
        );
    }

    if (error && !payload) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⚠️</div>
                <p style={{ color: 'var(--color-danger)', fontSize: '10px' }}>{error}</p>
            </div>
        );
    }

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">实时总览</h1>
                    <p className="page-subtitle">系统运行状态、资金收益与实时交易信息</p>
                </div>
                <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
                    最后更新: {currentTime.toLocaleString('zh-CN')}
                </div>
            </div>

            {/* 核心统计信息 */}
            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">当前时间</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {currentTime.toLocaleString('zh-CN')}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">机器人已运行</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {runtime.hours}小时{runtime.minutes}分{runtime.seconds}秒
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">运行模式</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {tradingMode === 'live' || tradingMode === '实盘' ? '🔴 实盘' : tradingMode === 'paper' || tradingMode === '模拟' ? '🟢 模拟' : '无'}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">初始资金</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {formatMoney(initialBalance)}
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">当前资金</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {formatMoney(currentBalance)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">净利润</div>
                    <div className="stat-num" style={{ fontSize: '13px', color: netProfit >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                        {netProfit >= 0 ? '+' : ''}{formatMoney(Math.abs(netProfit))}
                    </div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        收益率: {initialBalance > 0 ? ((netProfit / initialBalance) * 100).toFixed(2) : 0}%
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">交易策略</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {activeStrategies.length > 0 ? activeStrategies.join(' / ') : '无'}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">登录交易所</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {activeExchanges.length > 0 ? activeExchanges.map(e => e.toUpperCase()).join(' / ') : '无'}
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box" style={{ gridColumn: 'span 2' }}>
                    <div className="stat-label">交易币对选择</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {tradingPairs.length > 0 ? tradingPairs.slice(0, 10).join(', ') : '无'}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">机器人状态</div>
                    <div className="stat-num" style={{ fontSize: '12px' }}>
                        {summary.bot_status === 'running' ? '🟢 运行中' : summary.bot_status || '无'}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">数据刷新</div>
                    <div className="stat-num" style={{ fontSize: '11px' }}>
                        {payload?.last_refresh ? new Date(payload.last_refresh * 1000).toLocaleTimeString('zh-CN') : '实时'}
                    </div>
                </div>
            </div>

            {/* 实时收益曲线图 */}
            <div className="stat-box" style={{ height: '320px', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 500 }}>
                    实时收益曲线
                </h3>
                {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="90%">
                        <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                            <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                            <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                            <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                            <Legend />
                            <Line type="monotone" dataKey="balance" name="总资金 (USDT)" stroke="var(--cyan)" strokeWidth={2} dot={{ r: 2 }} />
                            <Line type="monotone" dataKey="profit" name="利润 (USDT)" stroke="var(--green)" strokeWidth={2} dot={{ r: 2 }} />
                        </LineChart>
                    </ResponsiveContainer>
                ) : (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px', marginTop: '60px' }}>
                        暂无收益曲线数据
                    </div>
                )}
            </div>

            {/* 实时买入卖出信息 */}
            <div className="stat-box">
                <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 500 }}>实时买入卖出信息</h3>
                <div className="data-table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>类型</th>
                                <th>方向</th>
                                <th>交易对</th>
                                <th>价格</th>
                                <th>数量</th>
                                <th>收益</th>
                                <th>交易所</th>
                            </tr>
                        </thead>
                        <tbody>
                            {tradeList.map((trade, idx) => {
                                const tradeTime = trade.timestamp ? new Date(trade.timestamp) : (trade.time ? new Date(trade.time) : new Date());
                                const sideLabel = trade.side === 'buy' ? '买入' : trade.side === 'sell' ? '卖出' : '无';
                                const sideColor = trade.side === 'buy' ? 'var(--color-profit)' : trade.side === 'sell' ? 'var(--color-loss)' : 'var(--text-muted)';
                                const profitValue = trade.profit || 0;
                                const profitColor = profitValue >= 0 ? 'var(--color-profit)' : 'var(--color-loss)';
                                
                                return (
                                    <tr key={`${trade.timestamp || trade.time}-${idx}`}>
                                        <td style={{ fontSize: '10px' }}>{tradeTime.toLocaleTimeString('zh-CN')}</td>
                                        <td style={{ fontSize: '10px' }}>
                                            <span style={{ 
                                                padding: '2px 6px', 
                                                borderRadius: '3px',
                                                background: trade.type === 'buy' ? 'rgba(0,200,100,0.1)' : 'rgba(200,0,0,0.1)',
                                                color: sideColor,
                                                fontWeight: '500'
                                            }}>
                                                {trade.type === 'buy' ? '买' : trade.type === 'sell' ? '卖' : '-'}
                                            </span>
                                        </td>
                                        <td style={{ fontSize: '10px', color: sideColor }}>{sideLabel}</td>
                                        <td style={{ fontSize: '10px', fontFamily: 'monospace' }}>{trade.symbol || '无'}</td>
                                        <td style={{ fontSize: '10px', fontFamily: 'monospace' }}>{trade.price ? trade.price.toFixed(4) : '0.0000'}</td>
                                        <td style={{ fontSize: '10px', fontFamily: 'monospace' }}>{trade.amount ? trade.amount.toFixed(6) : '0.000000'}</td>
                                        <td style={{ fontSize: '10px', fontFamily: 'monospace', color: profitColor, fontWeight: '500' }}>
                                            {profitValue >= 0 ? '+' : ''}{profitValue.toFixed(2)}
                                        </td>
                                        <td style={{ fontSize: '10px' }}>{trade.exchange || '无'}</td>
                                    </tr>
                                );
                            })}
                            {!tradeList.length && (
                                <tr>
                                    <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>
                                        暂无实时买入卖出信息
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

export default RealtimeOverview;
