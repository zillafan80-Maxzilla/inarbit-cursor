import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { configAPI, exchangeV2API, omsAPI, systemAPI } from '../api/client';

const formatMoney = (value, currency = 'USDT') => {
    const num = Number(value || 0);
    return `${currency}$${num.toFixed(2)}`;
};

const RealtimeOverview = () => {
    const [payload, setPayload] = useState(null);
    const [simPortfolio, setSimPortfolio] = useState(null);
    const [omsSummary, setOmsSummary] = useState(null);
    const [exchangeHealth, setExchangeHealth] = useState([]);
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

    // 加载模拟盘权益口径（统一 SimulationConfig/Portfolio/RealtimeOverview）
    useEffect(() => {
        let active = true;

        const loadPortfolio = async () => {
            try {
                const res = await configAPI.getSimulationPortfolio();
                if (!active) return;
                setSimPortfolio(res?.data || null);
            } catch {
                if (!active) return;
            }
        };

        const loadOms = async () => {
            try {
                const res = await omsAPI.getPnLSummary({ trading_mode: 'paper' });
                if (!active) return;
                setOmsSummary(res?.summary ?? res ?? null);
            } catch {
                if (!active) return;
                setOmsSummary(null);
            }
        };

        const loadExchangeHealth = async () => {
            try {
                const res = await exchangeV2API.health();
                if (!active) return;
                setExchangeHealth(Array.isArray(res?.data) ? res.data : []);
            } catch {
                if (!active) return;
                setExchangeHealth([]);
            }
        };

        loadPortfolio();
        loadOms();
        loadExchangeHealth();

        const t1 = setInterval(loadPortfolio, 5000);
        const t2 = setInterval(loadOms, 8000);
        const t3 = setInterval(loadExchangeHealth, 15000);

        return () => {
            active = false;
            clearInterval(t1);
            clearInterval(t2);
            clearInterval(t3);
        };
    }, []);

    const summary = payload?.summary || {};
    const currentTime = new Date(tick);
    
    const simSummary = simPortfolio?.summary || {};
    const quoteCurrency = simSummary.quoteCurrency || 'USDT';
    const initialBalance = Number(simSummary.initialCapital ?? summary.initial_capital ?? 1000);
    const totalEquity = Number(simSummary.totalEquity ?? initialBalance);
    const cashBalance = Number(simSummary.currentBalance ?? initialBalance);
    const positionsValue = Number(simSummary.totalValue ?? 0);
    const unrealizedPnL = Number(simSummary.unrealizedPnL ?? 0);
    const realizedPnL = Number(simSummary.realizedPnL ?? 0);
    const netProfit = totalEquity - initialBalance;

    const tradingMode = summary.trading_mode || 'paper';
    const botStatus = summary.bot_status || 'stopped';
    const activeStrategies = Array.isArray(summary.strategies) ? summary.strategies : [];

    const connectedExchangeCodes = exchangeHealth
        .filter((h) => h && h.is_connected === true)
        .map((h) => String(h.exchange_id || '').toUpperCase())
        .filter(Boolean);

    if (loading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载收益总览...</p>
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
                    <h1 className="page-title">收益总览</h1>
                    <p className="page-subtitle">资金收益与核心运行状态（权益口径已统一）</p>
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
                    <div className="stat-label">机器人状态</div>
                    <div className="stat-num" style={{ fontSize: '12px' }}>
                        {botStatus === 'running' ? '🟢 运行中' : botStatus === 'stopped' ? '🔴 已停止' : botStatus || '无'}
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
                        {formatMoney(initialBalance, quoteCurrency)}
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">总权益（模拟盘）</div>
                    <div className="stat-num" style={{ fontSize: '13px' }}>
                        {formatMoney(totalEquity, quoteCurrency)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">权益变化</div>
                    <div className="stat-num" style={{ fontSize: '13px', color: netProfit >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                        {netProfit >= 0 ? '+' : ''}{formatMoney(Math.abs(netProfit), quoteCurrency)}
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
                    <div className="stat-label">已连通交易所</div>
                    <div className="stat-num" style={{ fontSize: '11px', lineHeight: '1.4' }}>
                        {connectedExchangeCodes.length > 0 ? connectedExchangeCodes.join(' / ') : '无'}
                    </div>
                </div>
            </div>

            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">现金余额</div>
                    <div className="stat-num" style={{ fontSize: '12px' }}>
                        {formatMoney(cashBalance, quoteCurrency)}
                    </div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        说明：此处为模拟盘现金（可能包含对冲/卖出所得），并非总权益
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">仓位估值</div>
                    <div className="stat-num" style={{ fontSize: '12px' }}>
                        {formatMoney(positionsValue, quoteCurrency)}
                    </div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        未实现盈亏: {unrealizedPnL >= 0 ? '+' : ''}{formatMoney(Math.abs(unrealizedPnL), quoteCurrency)}
                        ，已实现盈亏: {realizedPnL >= 0 ? '+' : ''}{formatMoney(Math.abs(realizedPnL), quoteCurrency)}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">OMS 累计收益（模拟）</div>
                    <div className="stat-num" style={{ fontSize: '12px' }}>
                        {omsSummary ? `${Number(omsSummary.total_profit || 0) >= 0 ? '+' : ''}${Number(omsSummary.total_profit || 0).toFixed(4)} USDT` : '—'}
                    </div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        交易次数: {omsSummary ? Number(omsSummary.total_orders || 0) : '—'}，胜率: {omsSummary ? `${(Number(omsSummary.win_rate || 0) * 100).toFixed(2)}%` : '—'}
                    </div>
                </div>
            </div>

            {/* 去重说明 */}
            <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px', fontSize: '9px', color: 'var(--text-muted)' }}>
                <strong>说明：</strong> 本页以“模拟持仓/模拟配置”同一口径展示模拟盘总权益；交易明细与收益曲线请在“收益展示”页查看，避免重复。
            </div>
        </div>
    );
};

export default RealtimeOverview;
