/**
 * 模拟持仓页面
 * 重构版 - 按交易所分组显示，与实盘持仓样式一致
 */
import React, { useEffect, useState } from 'react';

import { useConnectedExchanges } from '../api/hooks';
import { configAPI } from '../api/client';

const Portfolio = () => {
    const { exchanges, loading } = useConnectedExchanges();
    const [portfolio, setPortfolio] = useState(null);
    const [error, setError] = useState('');
    const [refreshing, setRefreshing] = useState(false);

    const load = async () => {
        setRefreshing(true);
        setError('');
        try {
            const res = await configAPI.getSimulationPortfolio();
            setPortfolio(res?.data || null);
        } catch (e) {
            setError(String(e?.message || e));
        } finally {
            setRefreshing(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    const summary = portfolio?.summary || {};
    const exchangeAssets = portfolio?.exchanges || [];

    const positionsValue = Number(summary.totalValue || 0);
    const initialCapital = Number(summary.initialCapital || 0);
    const realizedPnL = Number(summary.realizedPnL || 0);
    const unrealizedPnL = Number(summary.unrealizedPnL || 0);
    const totalPnL = realizedPnL + unrealizedPnL;
    const pnlPercent = initialCapital ? ((totalPnL) / initialCapital * 100).toFixed(2) : '0.00';
    const quoteCurrency = summary.quoteCurrency || 'USDT';
    const displayCurrency = quoteCurrency;
    const cashBalance = Number(summary.currentBalance || 0);
    const totalEquity = Number(summary.totalEquity ?? (cashBalance + positionsValue));

    if (loading || refreshing) {
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
            <div className="page-header" style={{ marginBottom: '12px' }}>
                <div>
                    <h1 className="page-title">模拟持仓</h1>
                    <p className="page-subtitle">模拟账户资产组合（按交易所分组）</p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn btn-secondary" onClick={load}>🔄 刷新</button>
                </div>
            </div>

            {/* 模拟盘标识 */}
            <div style={{
                padding: '6px 10px',
                background: 'rgba(42, 161, 152, 0.08)',
                borderRadius: '5px',
                borderLeft: '3px solid #2aa198',
                fontSize: '9px',
                color: '#2aa198',
                marginBottom: '12px'
            }}>
                📝 模拟盘模式 - 所有交易均为虚拟
            </div>

            {/* 概览统计 */}
            {error && (
                <div className="stat-box" style={{ padding: '12px', color: 'var(--color-danger)', marginBottom: '12px' }}>{error}</div>
            )}

            <div className="stats-row" style={{ marginBottom: '12px' }}>
                <div className="stat-box">
                    <div className="stat-label">总权益</div>
                    <div className="stat-num highlight">{totalEquity.toFixed(2)} {displayCurrency}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">现金余额</div>
                    <div className="stat-num">{cashBalance.toFixed(2)} {displayCurrency}</div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        可能包含卖出/对冲所得现金（短仓会在仓位估值中体现为负值）
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">仓位估值</div>
                    <div className="stat-num">{positionsValue.toFixed(2)} {displayCurrency}</div>
                    <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        未实现盈亏: {unrealizedPnL >= 0 ? '+' : ''}{unrealizedPnL.toFixed(2)}，已实现盈亏: {realizedPnL >= 0 ? '+' : ''}{realizedPnL.toFixed(2)}
                    </div>
                </div>
            </div>

            <div className="stat-box" style={{ padding: '10px', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                <strong>口径说明：</strong> 总权益 = 现金余额 + 仓位估值。现货空头会表现为该币数量为负、仓位估值为负；永续(perp)仓位估值按“浮动盈亏”计入（避免把名义本金重复计入权益）。
            </div>

            {/* 交易所资产卡片 - 与实盘持仓样式一致 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '12px' }}>
                {(exchanges || []).map(exchange => {
                    const exchangeId = exchange.exchange_id || exchange.id;
                    const exData = exchangeAssets.find((ex) => ex.exchange_id === exchangeId) || { assets: [], totalValue: 0 };

                    return (
                        <div
                            key={exchange.id}
                            style={{
                                background: exchange.bgColor,
                                borderRadius: '10px',
                                border: `1px solid ${exchange.borderColor}25`,
                                borderLeft: `3px solid ${exchange.borderColor}`,
                                padding: '10px',
                                boxShadow: '0 1px 4px rgba(0,0,0,0.03)'
                            }}
                        >
                            {/* 卡片头部 - 交易所名称 */}
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                marginBottom: '10px',
                                paddingBottom: '6px',
                                borderBottom: `1px solid ${exchange.borderColor}15`
                            }}>
                                <span style={{ fontSize: '12px' }}>{exchange.icon}</span>
                                <span style={{ fontSize: '11px', fontWeight: 600, color: exchange.borderColor }}>
                                    {exchange.name}
                                </span>
                                <span style={{
                                    fontSize: '8px',
                                    color: '#2aa198',
                                    padding: '2px 5px',
                                    background: 'rgba(42, 161, 152, 0.1)',
                                    borderRadius: '3px',
                                    marginLeft: '4px'
                                }}>
                                    模拟
                                </span>
                                <span style={{
                                    marginLeft: 'auto',
                                    fontSize: '11px',
                                    fontWeight: 600,
                                    color: 'var(--text-primary)'
                                }}>
                                    {Number(exData.totalValue || 0).toFixed(2)} {quoteCurrency}
                                </span>
                            </div>

                            {/* 资产列表 - 紧凑版 */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                {exData.assets.map((asset, idx) => (
                                    <div key={idx} style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        padding: '5px 8px',
                                        background: 'rgba(255,255,255,0.6)',
                                        borderRadius: '5px',
                                        border: '1px solid rgba(0,0,0,0.03)',
                                        opacity: 1
                                    }}>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                <div style={{ fontSize: '10px', fontWeight: 600 }}>{asset.coin}</div>
                                                {asset.account_type && (
                                                    <span style={{ fontSize: '8px', padding: '1px 6px', borderRadius: '999px', background: 'rgba(0,0,0,0.04)', color: 'var(--text-muted)' }}>
                                                        {String(asset.account_type).toUpperCase()}
                                                    </span>
                                                )}
                                            </div>
                                            <div style={{ fontSize: '8px', color: 'var(--text-muted)' }}>
                                                价格: {asset.price !== null && asset.price !== undefined ? `${Number(asset.price).toLocaleString()}` : '-'}
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: '10px', fontWeight: 600 }}>
                                                <span style={{ color: Number(asset.quantity || 0) < 0 ? 'var(--color-danger)' : 'var(--text-primary)' }}>
                                                    {Number(asset.quantity || 0).toFixed(6)}
                                                </span>
                                            </div>
                                            <div style={{ fontSize: '8px', color: 'var(--text-muted)' }}>
                                                ≈ {asset.value !== null && asset.value !== undefined ? `${Number(asset.value).toFixed(2)}` : '-'} {quoteCurrency}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* 说明 */}
            <div style={{
                marginTop: '12px',
                padding: '8px',
                background: 'rgba(0,0,0,0.02)',
                borderRadius: '6px',
                fontSize: '9px',
                color: 'var(--text-muted)'
            }}>
                <strong>说明：</strong> 模拟持仓按交易所分组显示，数据来自模拟盘真实持仓与实时行情估值。
            </div>
        </div>
    );
};

export default Portfolio;
