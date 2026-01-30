/**
 * 策略配置管理页面
 * 重构版 - 横向列表布局（类似求职网站风格）
 */
import React, { useState } from 'react';
import { useStrategies, usePnLSummary, useSignals } from '../api/hooks';
import { strategyAPI } from '../api/client';

// 策略类型定义
const STRATEGY_TYPES = {
    triangular: {
        name: '三角套利',
        description: '检测 A→B→C→A 形式的价格差套利机会',
        algorithm: '数学计算',
        icon: '🔺',
        color: '#2aa198'
    },
    graph: {
        name: '图搜索套利',
        description: '使用 Bellman-Ford 算法动态发现负权环',
        algorithm: '贝尔曼-福特',
        icon: '🕸️',
        color: '#6c71c4'
    },
    funding_rate: {
        name: '期现套利',
        description: '利用永续合约资金费率进行对冲套利',
        algorithm: '资金费率监控',
        icon: '💹',
        color: '#b58900'
    },
    grid: {
        name: '网格交易',
        description: '在价格区间内布置网格，自动高抛低吸',
        algorithm: '区间震荡',
        icon: '📊',
        color: '#859900'
    },
    pair: {
        name: '配对交易',
        description: '基于 Z-Score 均值回归，监控相关币种价差',
        algorithm: 'Z 分数',
        icon: '🔄',
        color: '#d33682'
    }
};

const Strategies = () => {
    const { strategies, loading, error, refresh } = useStrategies();
    const { summary } = usePnLSummary();
    const { signals } = useSignals();
    const [updating, setUpdating] = useState(null);

    // 切换策略开关
    const toggleStrategy = async (id) => {
        setUpdating(id);
        try {
            await strategyAPI.toggle(id);
            await refresh();
        } catch (err) {
            alert(`更新失败: ${err.message}`);
        }
        setUpdating(null);
    };

    // 获取策略统计
    const getStrategyStats = (strategyType) => {
        const count = signals.filter(s => s.strategy_type === strategyType).length;
        return count;
    };

    if (loading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '11px' }}>加载策略配置中...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⚠️</div>
                <p style={{ color: 'var(--color-danger)', fontSize: '11px' }}>加载失败: {error}</p>
                <button onClick={refresh} className="btn btn-primary btn-sm" style={{ marginTop: '8px' }}>重试</button>
            </div>
        );
    }

    return (
        <div className="content-body">
            {/* 页面标题 */}
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">策略管理</h1>
                    <p className="page-subtitle">配置和管理交易策略</p>
                </div>
                <button onClick={refresh} className="btn btn-secondary btn-sm">🔄 刷新</button>
            </div>

            {/* 概览统计 */}
            <div className="stats-row" style={{ marginBottom: '16px' }}>
                <div className="stat-box">
                    <div className="stat-label">活跃策略</div>
                    <div className="stat-num" style={{ color: 'var(--color-success)' }}>
                        {strategies.filter(s => s.is_enabled).length}
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">今日信号</div>
                    <div className="stat-num">{signals.length}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">今日收益</div>
                    <div className="stat-num" style={{ color: summary.daily_pnl >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
                        {summary.daily_pnl >= 0 ? '+' : ''}{summary.daily_pnl?.toFixed(2) || '0'} USDT
                    </div>
                </div>
            </div>

            {/* 策略列表 - 横向布局 */}
            <div className="data-table-container">
                <div style={{ padding: '0' }}>
                    {strategies.map(strategy => {
                        const typeInfo = STRATEGY_TYPES[strategy.strategy_type] || {};
                        const signalCount = getStrategyStats(strategy.strategy_type);
                        const isUpdating = updating === strategy.id;

                        return (
                            <div
                                key={strategy.id}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '12px',
                                    padding: '12px 16px',
                                    borderBottom: '1px solid rgba(0,0,0,0.05)',
                                    background: strategy.is_enabled ? 'rgba(133, 153, 0, 0.03)' : 'transparent'
                                }}
                            >
                                {/* 左侧：图标 */}
                                <div style={{
                                    width: '36px',
                                    height: '36px',
                                    borderRadius: '8px',
                                    background: `${typeInfo.color}15`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: '16px',
                                    flexShrink: 0
                                }}>
                                    {typeInfo.icon}
                                </div>

                                {/* 中左：名称+描述 */}
                                <div style={{ flex: 2, minWidth: 0 }}>
                                    <div style={{
                                        fontSize: '12px',
                                        fontWeight: 600,
                                        color: 'var(--text-primary)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '6px'
                                    }}>
                                        {strategy.name || typeInfo.name}
                                        <span style={{
                                            fontSize: '8px',
                                            padding: '2px 6px',
                                            borderRadius: '4px',
                                            background: strategy.is_enabled ? 'rgba(133, 153, 0, 0.15)' : 'rgba(0,0,0,0.05)',
                                            color: strategy.is_enabled ? 'var(--color-success)' : 'var(--text-muted)'
                                        }}>
                                            {strategy.is_enabled ? '● 运行中' : '○ 已停止'}
                                        </span>
                                    </div>
                                    <div style={{
                                        fontSize: '9px',
                                        color: 'var(--text-muted)',
                                        marginTop: '2px',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        whiteSpace: 'nowrap'
                                    }}>
                                        {typeInfo.description}
                                    </div>
                                </div>

                                {/* 中右：参数 */}
                                <div style={{
                                    flex: 1,
                                    display: 'flex',
                                    gap: '16px',
                                    fontSize: '10px',
                                    color: 'var(--text-secondary)'
                                }}>
                                    <div>
                                        <div style={{ color: 'var(--text-muted)', fontSize: '8px' }}>信号</div>
                                        <div style={{ fontWeight: 600 }}>{signalCount}</div>
                                    </div>
                                    <div>
                                        <div style={{ color: 'var(--text-muted)', fontSize: '8px' }}>资金%</div>
                                        <div style={{ fontWeight: 600 }}>{(strategy.capital_percent * 100).toFixed(0)}%</div>
                                    </div>
                                    <div>
                                        <div style={{ color: 'var(--text-muted)', fontSize: '8px' }}>优先级</div>
                                        <div style={{ fontWeight: 600 }}>优先级 {strategy.priority}</div>
                                    </div>
                                </div>

                                {/* 右侧：操作按钮 */}
                                <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                                    <button
                                        onClick={() => toggleStrategy(strategy.id)}
                                        disabled={isUpdating}
                                        className={`btn btn-sm ${strategy.is_enabled ? 'btn-danger' : 'btn-primary'}`}
                                        style={{ minWidth: '60px' }}
                                    >
                                        {isUpdating ? '...' : (strategy.is_enabled ? '停止' : '启动')}
                                    </button>
                                    <button className="btn btn-sm btn-secondary">
                                        ⚙
                                    </button>
                                </div>
                            </div>
                        );
                    })}

                    {strategies.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '11px' }}>
                            尚未配置任何策略
                        </div>
                    )}
                </div>
            </div>

            {/* 说明 */}
            <div style={{
                marginTop: '12px',
                padding: '10px',
                background: 'rgba(0,0,0,0.02)',
                borderRadius: '6px',
                fontSize: '9px',
                color: 'var(--text-muted)'
            }}>
                <strong>策略说明：</strong> 启动机器人时默认使用三角套利策略。可同时启用多个策略，系统会根据优先级和市场情况自动调度。
            </div>
        </div>
    );
};

export default Strategies;
