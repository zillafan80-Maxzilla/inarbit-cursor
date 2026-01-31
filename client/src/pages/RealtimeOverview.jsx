import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

import { systemAPI } from '../api/client';

const POLL_INTERVAL_MS = 5000;

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

const formatTradeSide = (side) => {
    if (side === 'buy') return '买入';
    if (side === 'sell') return '卖出';
    return '无';
};

const RealtimeOverview = () => {
    const [payload, setPayload] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [uptimeBase, setUptimeBase] = useState({ seconds: 0, ts: 0 });
    const [tick, setTick] = useState(Date.now());

    useEffect(() => {
        const timer = setInterval(() => setTick(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        let active = true;
        const load = async (force = false) => {
            try {
                const res = await systemAPI.realtime(force);
                if (!active) return;
                const data = res?.data || res || {};
                setPayload(data);
                setUptimeBase({ seconds: Number(data.uptime_seconds || 0), ts: Date.now() });
                setError(null);
            } catch (e) {
                if (!active) return;
                setError(e.message || '加载失败');
            } finally {
                if (active) setLoading(false);
            }
        };

        load(true);
        const interval = setInterval(() => load(false), POLL_INTERVAL_MS);
        return () => {
            active = false;
            clearInterval(interval);
        };
    }, []);

    const summary = payload?.summary || {};
    const currentTime = new Date(tick);
    const uptimeSeconds = useMemo(() => {
        if (!uptimeBase.ts) return Number(payload?.uptime_seconds || 0);
        const delta = Math.floor((tick - uptimeBase.ts) / 1000);
        return Math.max(0, uptimeBase.seconds + delta);
    }, [payload, tick, uptimeBase]);

    const tradingMode = summary.trading_mode === 'live' ? '实盘' : summary.trading_mode === 'paper' ? '模拟' : '无';
    const strategiesText = (summary.strategies || []).length ? summary.strategies.join(' / ') : '无';
    const exchangesText = (summary.exchanges || []).length ? summary.exchanges.join(' / ') : '无';
    const pairsText = (summary.pairs || []).length ? summary.pairs.join(' / ') : '无';
    const currency = summary.quote_currency || 'USDT';

    const profitCurve = Array.isArray(payload?.profit_curve) ? payload.profit_curve : [];
    const chartData = useMemo(() => {
        return profitCurve.map((pt) => {
            const ts = pt.timestamp ? new Date(pt.timestamp) : new Date();
            const label = ts.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            return { time: label, value: Number(pt.value || 0) };
        });
    }, [profitCurve]);

    const trades = Array.isArray(payload?.trades) ? payload.trades : [];

    if (loading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载实时概览...</p>
            </div>
        );
    }

    if (error) {
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
                    <p className="page-subtitle">登录后默认展示机器人运行状态与收益信息</p>
                </div>
            </div>

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
                        {formatUptime(uptimeSeconds)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">当前运行模式</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {tradingMode === '实盘' ? '🔴 实盘' : tradingMode === '模拟' ? '🟢 模拟' : '无'}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">交易策略</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {strategiesText}
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">登录交易所</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {exchangesText}
                    </div>
                </div>
                <div className="stat-box" style={{ gridColumn: 'span 2' }}>
                    <div className="stat-label">交易币对选择</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {pairsText}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">初始资金</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {formatMoney(summary.initial_capital, currency)}
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">当前收益资金</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {formatMoney(summary.current_balance, currency)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">净利润</div>
                    <div className="stat-num" style={{ fontSize: '13px', color: Number(summary.net_profit || 0) >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                        {formatMoney(summary.net_profit, currency)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">机器人状态</div>
                    <div className="stat-num" style={{ fontSize: '12px' }}>
                        {summary.bot_status === 'running' ? '运行中' : summary.bot_status || '无'}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">数据刷新时间</div>
                    <div className="stat-num" style={{ fontSize: '11px' }}>
                        {payload?.last_refresh ? new Date(payload.last_refresh * 1000).toLocaleTimeString('zh-CN') : '无'}
                    </div>
                </div>
            </div>

            <div className="stat-box" style={{ height: '260px', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 500 }}>
                    实时收益曲线图
                </h3>
                <ResponsiveContainer width="100%" height="90%">
                    <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                        <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                        <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                        <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                        <Line type="monotone" dataKey="value" name="净利润" stroke="var(--cyan)" strokeWidth={2} dot={{ r: 2 }} />
                    </LineChart>
                </ResponsiveContainer>
                {!chartData.length && (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px', marginTop: '8px' }}>
                        暂无收益曲线数据
                    </div>
                )}
            </div>

            <div className="stat-box">
                <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 500 }}>实时买入卖出信息</h3>
                <div className="data-table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>方向</th>
                                <th>交易对</th>
                                <th>价格</th>
                                <th>数量</th>
                                <th>交易所</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trades.map((trade, idx) => {
                                const tradeTime = trade.time ? new Date(trade.time) : new Date();
                                const sideLabel = formatTradeSide(trade.side);
                                const sideColor = trade.side === 'buy' ? 'var(--color-profit)' : trade.side === 'sell' ? 'var(--color-loss)' : 'var(--text-muted)';
                                return (
                                    <tr key={`${trade.time}-${idx}`}>
                                        <td style={{ fontSize: '10px' }}>{tradeTime.toLocaleTimeString('zh-CN')}</td>
                                        <td style={{ fontSize: '10px', color: sideColor }}>{sideLabel}</td>
                                        <td style={{ fontSize: '10px' }}>{trade.symbol || '无'}</td>
                                        <td style={{ fontSize: '10px' }}>{trade.price ? trade.price.toFixed(4) : '无'}</td>
                                        <td style={{ fontSize: '10px' }}>{trade.amount ? trade.amount.toFixed(6) : '无'}</td>
                                        <td style={{ fontSize: '10px' }}>{trade.exchange || '无'}</td>
                                    </tr>
                                );
                            })}
                            {!trades.length && (
                                <tr>
                                    <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>
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
