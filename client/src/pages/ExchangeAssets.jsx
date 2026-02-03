/**
 * 实盘持仓页面
 * 重构版 - 使用统一的Solarized配色交易所卡片
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useConnectedExchanges } from '../api/hooks';
import { exchangeV2API } from '../api/client';

const ExchangeAssets = () => {
    const [searchParams] = useSearchParams();
    const { exchanges, loading: exchangesLoading } = useConnectedExchanges();
    const [loading, setLoading] = useState(true);
    const [assetsData, setAssetsData] = useState({});
    const [error, setError] = useState('');
    const [exchangeConfigs, setExchangeConfigs] = useState([]);
    const [lastUpdated, setLastUpdated] = useState(null);

    useEffect(() => {
        const loadConfigs = async () => {
            try {
                const resp = await exchangeV2API.list();
                const list = Array.isArray(resp) ? resp : (resp?.data || []);
                const activeList = list.filter((item) => item.is_active && !item.deleted_at);
                setExchangeConfigs(activeList);
            } catch (e) {
                setError(String(e?.message || e));
            }
        };
        loadConfigs();
    }, []);

    const filterId = useMemo(() => searchParams.get('exchange_id') || '', [searchParams]);

    const displayExchanges = useMemo(() => {
        if (!exchangeConfigs.length) return [];
        const styleMap = new Map((exchanges || []).map((ex) => [ex.id, ex]));
        const list = exchangeConfigs.map((cfg) => {
            const styled = styleMap.get(cfg.exchange_id);
            return {
                id: cfg.exchange_id,
                configId: cfg.id,
                name: styled?.name || cfg.display_name || cfg.exchange_id,
                icon: styled?.icon || '🔵',
                bgColor: styled?.bgColor || 'rgba(0,0,0,0.06)',
                borderColor: styled?.borderColor || '#666666',
                displayName: cfg.display_name || cfg.exchange_id
            };
        });
        if (filterId && list.some((item) => item.configId === filterId)) {
            return list.filter((item) => item.configId === filterId);
        }
        return list;
    }, [exchangeConfigs, exchanges, filterId]);

    const loadAssets = useCallback(async () => {
        if (exchangesLoading) return;
        if (!exchangeConfigs || exchangeConfigs.length === 0) {
            setLoading(false);
            return;
        }

        setLoading(true);
        setError('');
        const next = {};

        for (const ex of displayExchanges || []) {
            const configId = ex.configId;
            if (!configId) {
                next[ex.id] = { totalValue: 0, assets: [], error: '未找到交易所配置' };
                continue;
            }
            try {
                const data = await exchangeV2API.assets(configId);
                next[ex.id] = {
                    totalValue: data?.total_value_usdt || 0,
                    assets: data?.assets || [],
                    error: ''
                };
            } catch (e) {
                next[ex.id] = { totalValue: 0, assets: [], error: String(e?.message || e) };
            }
        }

        setAssetsData(next);
        setLastUpdated(new Date());
        setLoading(false);
    }, [exchangesLoading, exchangeConfigs, displayExchanges]);

    useEffect(() => {
        // eslint 规则禁止在 effect 内同步触发 setState 链式更新
        // 这里用异步调度以避免“set-state-in-effect”误报
        const t = setTimeout(() => loadAssets(), 0);
        return () => clearTimeout(t);
    }, [loadAssets]);

    useEffect(() => {
        const timer = setInterval(() => {
            loadAssets();
        }, 30000);
        return () => clearInterval(timer);
    }, [loadAssets]);

    const totalAllAssets = Object.values(assetsData).reduce((sum, ex) => sum + (ex.totalValue || 0), 0);
    const connectedCount = (displayExchanges || []).length;

    const formatQty = (value, digits = 4) => {
        const num = Number(value || 0);
        if (!Number.isFinite(num)) return '0.0000';
        return num.toFixed(digits);
    };

    if (loading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载实盘资产...</p>
            </div>
        );
    }

    if (!connectedCount) {
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
                    <h1 className="page-title">实盘持仓</h1>
                    <p className="page-subtitle">交易所真实资金与持仓</p>
                </div>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                    {lastUpdated && (
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                            更新于 {lastUpdated.toLocaleTimeString()}
                        </span>
                    )}
                    <button onClick={loadAssets} className="btn btn-secondary">🔄 刷新</button>
                </div>
            </div>

            {/* 警告提示 */}
            <div style={{
                padding: '6px 10px',
                background: 'rgba(220, 50, 47, 0.08)',
                borderRadius: '5px',
                borderLeft: '3px solid var(--color-danger)',
                fontSize: '9px',
                color: 'var(--color-danger)',
                marginBottom: '12px'
            }}>
                ⚠️ 实盘账户数据，请谨慎操作
            </div>

            {/* 概览统计 */}
            <div className="stats-row" style={{ marginBottom: '12px' }}>
                <div className="stat-box">
                    <div className="stat-label">总资产估值</div>
                    <div className="stat-num highlight">${totalAllAssets.toLocaleString()}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">已连接交易所</div>
                    <div className="stat-num">{connectedCount}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">资产刷新</div>
                    <div className="stat-num" style={{ color: 'var(--color-success)' }}>实时</div>
                </div>
            </div>

            {error && (
                <div style={{
                    padding: '8px 10px',
                    marginBottom: '12px',
                    background: 'rgba(220, 50, 47, 0.08)',
                    borderRadius: '6px',
                    fontSize: '10px',
                    color: 'var(--color-danger)'
                }}>
                    {error}
                </div>
            )}

            {/* 交易所资产卡片 - 使用Solarized配色 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '12px' }}>
                {(displayExchanges || []).map(exchange => {
                    const exData = assetsData[exchange.id] || { assets: [], totalValue: 0, error: '' };

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
                            {/* 卡片头部 */}
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
                                    marginLeft: 'auto',
                                    fontSize: '11px',
                                    fontWeight: 600,
                                    color: 'var(--text-primary)'
                                }}>
                                    ${exData.totalValue.toLocaleString()}
                                </span>
                            </div>

                            {exData.error && (
                                <div style={{
                                    marginBottom: '8px',
                                    fontSize: '9px',
                                    color: 'var(--color-danger)'
                                }}>
                                    {exData.error}
                                </div>
                            )}

                            {/* 资产列表 - 紧凑版 */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                {exData.assets.map((asset, idx) => (
                                    <div key={idx} style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        padding: '5px 8px',
                                        background: 'rgba(255,255,255,0.6)',
                                        borderRadius: '5px',
                                        border: '1px solid rgba(0,0,0,0.03)'
                                    }}>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontSize: '10px', fontWeight: 600 }}>{asset.coin}</div>
                                            <div style={{ fontSize: '8px', color: 'var(--text-muted)' }}>
                                                可用: {formatQty(asset.free)} | 冻结: {formatQty(asset.locked)}
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div style={{ fontSize: '10px', fontWeight: 600 }}>
                                                {formatQty(asset.total)}
                                            </div>
                                            <div style={{ fontSize: '8px', color: 'var(--text-muted)' }}>
                                                {asset.value_usdt != null ? `≈ $${formatQty(asset.value_usdt, 2)}` : '≈ -'}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                                {exData.assets.length === 0 && (
                                    <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>暂无资产数据</div>
                                )}
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
                <strong>说明：</strong> 实盘资产从交易所接口获取，页面默认每 30 秒自动刷新。
            </div>
        </div>
    );
};

export default ExchangeAssets;
