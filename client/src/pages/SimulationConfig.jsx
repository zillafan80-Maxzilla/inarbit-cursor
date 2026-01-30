import React, { useEffect, useState } from 'react';

import { configAPI } from '../api/client';

/**
 * 模拟配置页面
 * 重构版 - 与Portfolio数据统一
 */
const SimulationConfig = () => {
    const [config, setConfig] = useState({
        initialCapital: 1000,
        quoteCurrency: 'USDT',
        resetOnStart: false
    });

    const [paperStats, setPaperStats] = useState({
        initialCapital: 1000,
        currentBalance: 1000,
        realizedPnL: 0,
        unrealizedPnL: 0,
        winRate: 0,
        totalTrades: 0,
        quoteCurrency: 'USDT',
        totalEquity: null
    });

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [resetting, setResetting] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const [configRes, portfolioRes] = await Promise.all([
                configAPI.getSimulationConfig(),
                configAPI.getSimulationPortfolio(),
            ]);
            const data = configRes?.data || {};
            const summary = portfolioRes?.data?.summary || {};
            setConfig({
                initialCapital: data.initialCapital ?? 1000,
                quoteCurrency: data.quoteCurrency || 'USDT',
                resetOnStart: !!data.resetOnStart,
            });
            setPaperStats({
                initialCapital: summary.initialCapital ?? data.initialCapital ?? 1000,
                currentBalance: summary.currentBalance ?? data.currentBalance ?? 1000,
                realizedPnL: summary.realizedPnL ?? data.realizedPnL ?? 0,
                unrealizedPnL: summary.unrealizedPnL ?? data.unrealizedPnL ?? 0,
                winRate: summary.winRate ?? data.winRate ?? 0,
                totalTrades: summary.totalTrades ?? data.totalTrades ?? 0,
                quoteCurrency: summary.quoteCurrency || data.quoteCurrency || 'USDT',
                totalEquity: summary.totalEquity,
            });
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    const handleSave = async () => {
        setSaving(true);
        try {
            await configAPI.updateSimulationConfig({
                initialCapital: config.initialCapital,
                quoteCurrency: config.quoteCurrency,
                resetOnStart: config.resetOnStart,
            });
            await load();
            alert('配置已保存');
        } catch (e) {
            alert(e.message || '保存失败');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = async () => {
        if (!confirm('确认立即重置模拟盘？此操作会清空模拟盘收益与持仓数据。')) return;
        setResetting(true);
        try {
            await configAPI.updateSimulationConfig({
                resetNow: true,
            });
            await load();
            alert('模拟盘已重置');
        } catch (e) {
            alert(e.message || '重置失败');
        } finally {
            setResetting(false);
        }
    };

    // 计算当前总权益（后端返回优先）
    const totalEquity = paperStats.totalEquity ?? (
        paperStats.currentBalance + paperStats.realizedPnL + paperStats.unrealizedPnL
    );

    return (
        <div className="content-body">
            <h2 className="section-title">模拟盘配置</h2>

            {/* 实时模拟报表 */}
            <div className="stat-box" style={{ marginBottom: '1.5rem' }}>
                <h3 style={{ fontSize: '12px', color: '#2aa198', marginBottom: '12px' }}>当前模拟账户状态</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', opacity: loading ? 0.6 : 1 }}>
                    <div>
                        <div className="stat-label">总权益</div>
                        <div className="stat-num">${totalEquity.toFixed(2)}</div>
                    </div>
                    <div>
                        <div className="stat-label">未实现盈亏</div>
                        <div className="stat-num" style={{ color: paperStats.unrealizedPnL >= 0 ? '#859900' : '#dc322f' }}>
                            {paperStats.unrealizedPnL >= 0 ? '+' : ''}${paperStats.unrealizedPnL.toFixed(2)}
                        </div>
                    </div>
                    <div>
                        <div className="stat-label">已实现盈亏</div>
                        <div className="stat-num highlight">+${paperStats.realizedPnL.toFixed(2)}</div>
                    </div>
                    <div>
                        <div className="stat-label">胜率</div>
                        <div className="stat-num">{(paperStats.winRate * 100).toFixed(1)}%</div>
                    </div>
                </div>
            </div>

            {/* 配置表单 */}
            <div className="stat-box">
                <h3 style={{ fontSize: '12px', color: '#586e75', marginBottom: '12px' }}>初始化设置</h3>

                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', marginBottom: '6px', color: '#657b83', fontSize: '10px' }}>初始模拟资金</label>
                    <input
                        type="number"
                        value={config.initialCapital}
                        onChange={(e) => setConfig({ ...config, initialCapital: parseFloat(e.target.value) })}
                        style={{ padding: '6px', width: '150px', marginRight: '8px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)', fontSize: '11px' }}
                    />
                    <select
                        value={config.quoteCurrency}
                        onChange={(e) => setConfig({ ...config, quoteCurrency: e.target.value })}
                        style={{ padding: '6px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)', fontSize: '11px' }}
                    >
                        <option value="USDT">USDT</option>
                        <option value="USDC">USDC</option>
                        <option value="BTC">BTC</option>
                    </select>
                </div>

                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83' }}>
                        <input
                            type="checkbox"
                            checked={config.resetOnStart}
                            onChange={(e) => setConfig({ ...config, resetOnStart: e.target.checked })}
                        />
                        下次启动时重置账户
                    </label>
                </div>

                <div style={{ borderTop: '1px solid rgba(0,0,0,0.05)', paddingTop: '12px', display: 'flex', justifyContent: 'space-between' }}>
                    <button className="btn btn-danger btn-sm" disabled={resetting} onClick={handleReset}>
                        {resetting ? '重置中...' : '⚠️ 立即重置模拟盘'}
                    </button>
                    <button className="btn btn-primary btn-sm" disabled={saving} onClick={handleSave}>
                        {saving ? '保存中...' : '保存配置'}
                    </button>
                </div>
            </div>

            {/* 说明 */}
            <div style={{ marginTop: '12px', padding: '10px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px', fontSize: '9px', color: 'var(--text-muted)' }}>
                <strong>说明：</strong> 总权益 = 当前余额 + 已实现盈亏 + 未实现盈亏。所有数据来自模拟盘实时账户。
            </div>
        </div>
    );
};

export default SimulationConfig;
