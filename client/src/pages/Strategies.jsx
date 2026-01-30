/**
 * 策略配置管理页面
 * 重构版 - 横向列表布局（类似求职网站风格）
 */
import React, { useEffect, useState } from 'react';
import { useStrategies, usePnLSummary, useSignals } from '../api/hooks';
import { configAPI, strategyAPI, systemAPI } from '../api/client';

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

const OPPORTUNITY_TYPES = ['graph', 'grid', 'pair'];
const DEFAULT_REGIME_WEIGHTS = {
    RANGE: 1.0,
    DOWNTREND: 0.6,
    UPTREND: 0.7,
    STRESS: 0.2,
};

const Strategies = () => {
    const { strategies, loading, error, refresh } = useStrategies();
    const { summary } = usePnLSummary();
    const { signals } = useSignals();
    const [updating, setUpdating] = useState(null);
    const [savingStrategy, setSavingStrategy] = useState({});
    const [opportunityConfigs, setOpportunityConfigs] = useState({});
    const [opportunityLoading, setOpportunityLoading] = useState(false);
    const [opportunitySaving, setOpportunitySaving] = useState({});
    const [opportunityHistory, setOpportunityHistory] = useState({});
    const [opportunityTemplates, setOpportunityTemplates] = useState({});
    const [templateDrafts, setTemplateDrafts] = useState({});
    const [regimeMetrics, setRegimeMetrics] = useState(null);
    const [strategyDrafts, setStrategyDrafts] = useState({});

    // 切换策略开关
    const toggleStrategy = async (id) => {
        setUpdating(id);
        try {
            await strategyAPI.toggle(id);
            await strategyAPI.reload();
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

    const loadOpportunityConfigs = async () => {
        setOpportunityLoading(true);
        try {
            const results = await Promise.all(
                OPPORTUNITY_TYPES.map((type) => configAPI.getOpportunityConfig(type))
            );
            const next = {};
            results.forEach((res, index) => {
                const type = OPPORTUNITY_TYPES[index];
                const cfg = res?.data?.config || {};
                next[type] = {
                    raw: JSON.stringify(cfg, null, 2),
                    version: res?.data?.version || 1,
                };
            });
            setOpportunityConfigs(next);
        } catch (err) {
            alert(`加载机会配置失败: ${err.message}`);
        } finally {
            setOpportunityLoading(false);
        }
    };

    const loadRegimeMetrics = async () => {
        try {
            const res = await systemAPI.metrics();
            setRegimeMetrics(res?.data?.market_regime || null);
        } catch (err) {
            setRegimeMetrics(null);
        }
    };

    const saveStrategyRouting = async (strategyId) => {
        const strategy = strategies.find((s) => s.id === strategyId);
        if (!strategy) return;
        const draft = strategyDrafts[strategyId] || {};
        const parsedLeverage = Number(draft.max_leverage);
        const maxLeverage = Number.isFinite(parsedLeverage) ? parsedLeverage : 1;
        const weightInput = draft.regime_weights || {};
        const normalizedWeights = Object.keys(DEFAULT_REGIME_WEIGHTS).reduce((acc, key) => {
            const raw = weightInput[key];
            const parsed = Number(raw);
            acc[key] = Number.isFinite(parsed) ? parsed : DEFAULT_REGIME_WEIGHTS[key];
            return acc;
        }, {});
        const merged = {
            ...(strategy.config || {}),
            allow_short: !!draft.allow_short,
            max_leverage: maxLeverage,
            regime_weights: normalizedWeights,
        };
        setSavingStrategy((prev) => ({ ...prev, [strategyId]: true }));
        try {
            await strategyAPI.update(strategyId, { config: merged });
            await refresh();
        } catch (err) {
            alert(`保存策略路由失败: ${err.message}`);
        } finally {
            setSavingStrategy((prev) => ({ ...prev, [strategyId]: false }));
        }
    };

    const saveOpportunityConfig = async (type) => {
        const payload = opportunityConfigs[type]?.raw || '{}';
        setOpportunitySaving((prev) => ({ ...prev, [type]: true }));
        try {
            const parsed = JSON.parse(payload);
            const res = await configAPI.updateOpportunityConfig(type, { config: parsed });
            setOpportunityConfigs((prev) => ({
                ...prev,
                [type]: {
                    raw: JSON.stringify(res?.data?.config || {}, null, 2),
                    version: res?.data?.version || prev[type]?.version || 1,
                },
            }));
            await loadOpportunityHistory(type);
        } catch (err) {
            alert(`保存 ${type} 配置失败: ${err.message}`);
        } finally {
            setOpportunitySaving((prev) => ({ ...prev, [type]: false }));
        }
    };

    const loadOpportunityHistory = async (type) => {
        try {
            const res = await configAPI.getOpportunityConfigHistory(type, { limit: 20 });
            setOpportunityHistory((prev) => ({ ...prev, [type]: res?.history || [] }));
        } catch (err) {
            alert(`加载 ${type} 历史失败: ${err.message}`);
        }
    };

    const rollbackOpportunityConfig = async (type, version) => {
        if (!version) return;
        try {
            const res = await configAPI.rollbackOpportunityConfig(type, { version: Number(version) });
            setOpportunityConfigs((prev) => ({
                ...prev,
                [type]: {
                    raw: JSON.stringify(res?.data?.config || {}, null, 2),
                    version: res?.data?.version || prev[type]?.version || 1,
                    rollbackVersion: '',
                },
            }));
            await loadOpportunityHistory(type);
        } catch (err) {
            alert(`回滚 ${type} 失败: ${err.message}`);
        }
    };

    const loadOpportunityTemplates = async (type) => {
        try {
            const res = await configAPI.listOpportunityTemplates({ strategy_type: type });
            setOpportunityTemplates((prev) => ({ ...prev, [type]: res?.templates || [] }));
        } catch (err) {
            alert(`加载 ${type} 模板失败: ${err.message}`);
        }
    };

    const createOpportunityTemplate = async (type) => {
        const draft = templateDrafts[type] || {};
        const raw = opportunityConfigs[type]?.raw || '{}';
        if (!draft.name) {
            alert('请输入模板名称');
            return;
        }
        try {
            const parsed = JSON.parse(raw);
            await configAPI.createOpportunityTemplate({
                strategyType: type,
                name: draft.name,
                description: draft.description || '',
                config: parsed,
            });
            setTemplateDrafts((prev) => ({
                ...prev,
                [type]: { name: '', description: '' },
            }));
            await loadOpportunityTemplates(type);
        } catch (err) {
            alert(`创建模板失败: ${err.message}`);
        }
    };

    const applyOpportunityTemplate = async (type, templateId) => {
        try {
            const res = await configAPI.applyOpportunityTemplate(type, templateId);
            setOpportunityConfigs((prev) => ({
                ...prev,
                [type]: {
                    raw: JSON.stringify(res?.data?.config || {}, null, 2),
                    version: res?.data?.version || prev[type]?.version || 1,
                },
            }));
            await loadOpportunityHistory(type);
        } catch (err) {
            alert(`应用模板失败: ${err.message}`);
        }
    };

    useEffect(() => {
        loadOpportunityConfigs();
        loadRegimeMetrics();
    }, []);

    useEffect(() => {
        const drafts = {};
        strategies.forEach((s) => {
            const cfg = s.config || {};
            const weights = { ...DEFAULT_REGIME_WEIGHTS, ...(cfg.regime_weights || {}) };
            drafts[s.id] = {
                allow_short: cfg.allow_short ?? false,
                max_leverage: cfg.max_leverage ?? 1,
                regime_weights: {
                    RANGE: weights.RANGE,
                    DOWNTREND: weights.DOWNTREND,
                    UPTREND: weights.UPTREND,
                    STRESS: weights.STRESS,
                },
            };
        });
        setStrategyDrafts(drafts);
    }, [strategies]);

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
                <div className="stat-box">
                    <div className="stat-label">市场状态</div>
                    <div className="stat-num">{regimeMetrics?.regime || '-'}</div>
                </div>
            </div>

            {/* 策略列表 - 横向布局 */}
            <div className="data-table-container">
                <div style={{ padding: '0' }}>
                    {strategies.map(strategy => {
                        const typeInfo = STRATEGY_TYPES[strategy.strategy_type] || {};
                        const signalCount = getStrategyStats(strategy.strategy_type);
                        const isUpdating = updating === strategy.id;
                        const draft = strategyDrafts[strategy.id] || {};

                        return (
                            <div key={strategy.id} style={{ borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
                                <div
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '12px',
                                        padding: '12px 16px',
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
                                        <button
                                            onClick={() => saveStrategyRouting(strategy.id)}
                                            className="btn btn-sm btn-secondary"
                                            disabled={savingStrategy[strategy.id]}
                                        >
                                            {savingStrategy[strategy.id] ? '保存中' : '保存'}
                                        </button>
                                    </div>
                                </div>
                                <div style={{ padding: '0 16px 12px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            <input
                                                type="checkbox"
                                                checked={!!draft.allow_short}
                                                onChange={(e) => setStrategyDrafts((prev) => ({
                                                    ...prev,
                                                    [strategy.id]: { ...prev[strategy.id], allow_short: e.target.checked },
                                                }))}
                                            />
                                            允许做空
                                        </label>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            最大杠杆
                                            <input
                                                className="form-input"
                                                value={draft.max_leverage ?? 1}
                                                onChange={(e) => setStrategyDrafts((prev) => ({
                                                    ...prev,
                                                    [strategy.id]: { ...prev[strategy.id], max_leverage: e.target.value },
                                                }))}
                                                style={{ width: '70px', height: '24px' }}
                                            />
                                        </label>
                                        {['RANGE', 'DOWNTREND', 'UPTREND', 'STRESS'].map((key) => (
                                            <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                {key}
                                                <input
                                                    className="form-input"
                                                    value={draft.regime_weights?.[key] ?? DEFAULT_REGIME_WEIGHTS[key]}
                                                    onChange={(e) => setStrategyDrafts((prev) => ({
                                                        ...prev,
                                                        [strategy.id]: {
                                                            ...prev[strategy.id],
                                                            regime_weights: {
                                                                ...(prev[strategy.id]?.regime_weights || {}),
                                                                [key]: e.target.value,
                                                            },
                                                        },
                                                    }))}
                                                    style={{ width: '60px', height: '24px' }}
                                                />
                                            </label>
                                        ))}
                                    </div>
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

            {/* 机会配置 */}
            <div style={{ marginTop: '20px' }}>
                <div className="page-header" style={{ marginBottom: '12px' }}>
                    <div>
                        <h2 className="page-title" style={{ fontSize: '14px' }}>机会配置</h2>
                        <p className="page-subtitle">管理 Graph/Grid/Pair 机会参数</p>
                    </div>
                    <button
                        onClick={loadOpportunityConfigs}
                        className="btn btn-secondary btn-sm"
                        disabled={opportunityLoading}
                    >
                        {opportunityLoading ? '加载中...' : '刷新配置'}
                    </button>
                </div>

                <div className="data-table-container" style={{ padding: '12px' }}>
                    {OPPORTUNITY_TYPES.map((type) => {
                        const typeInfo = STRATEGY_TYPES[type] || {};
                        const configText = opportunityConfigs[type]?.raw || '{}';
                        const version = opportunityConfigs[type]?.version || 1;
                        return (
                            <div
                                key={type}
                                style={{
                                    border: '1px solid rgba(0,0,0,0.06)',
                                    borderRadius: '8px',
                                    padding: '12px',
                                    marginBottom: '12px',
                                    background: 'rgba(0,0,0,0.01)',
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                                    <div style={{ fontSize: '12px', fontWeight: 600 }}>
                                        {typeInfo.icon} {typeInfo.name || type} <span style={{ color: 'var(--text-muted)', fontSize: '9px' }}>v{version}</span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => loadOpportunityHistory(type)}
                                        >
                                            历史
                                        </button>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => loadOpportunityTemplates(type)}
                                        >
                                            模板
                                        </button>
                                        <button
                                            className="btn btn-primary btn-sm"
                                            onClick={() => saveOpportunityConfig(type)}
                                            disabled={opportunitySaving[type]}
                                        >
                                            {opportunitySaving[type] ? '保存中...' : '保存'}
                                        </button>
                                    </div>
                                </div>
                                <textarea
                                    value={configText}
                                    onChange={(e) => setOpportunityConfigs((prev) => ({
                                        ...prev,
                                        [type]: {
                                            ...prev[type],
                                            raw: e.target.value,
                                        },
                                    }))}
                                    style={{
                                        marginTop: '8px',
                                        width: '100%',
                                        minHeight: '120px',
                                        fontSize: '10px',
                                        fontFamily: 'monospace',
                                        borderRadius: '6px',
                                        border: '1px solid rgba(0,0,0,0.08)',
                                        padding: '8px',
                                    }}
                                />
                                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px', flexWrap: 'wrap' }}>
                                    <input
                                        className="form-input"
                                        placeholder="回滚版本号"
                                        value={opportunityConfigs[type]?.rollbackVersion || ''}
                                        onChange={(e) => setOpportunityConfigs((prev) => ({
                                            ...prev,
                                            [type]: {
                                                ...prev[type],
                                                rollbackVersion: e.target.value,
                                            },
                                        }))}
                                        style={{ minWidth: '120px', height: '26px' }}
                                    />
                                    <button
                                        className="btn btn-sm btn-danger"
                                        onClick={() => rollbackOpportunityConfig(type, opportunityConfigs[type]?.rollbackVersion)}
                                    >
                                        回滚
                                    </button>
                                    <input
                                        className="form-input"
                                        placeholder="模板名称"
                                        value={templateDrafts[type]?.name || ''}
                                        onChange={(e) => setTemplateDrafts((prev) => ({
                                            ...prev,
                                            [type]: { ...prev[type], name: e.target.value },
                                        }))}
                                        style={{ minWidth: '140px', height: '26px' }}
                                    />
                                    <input
                                        className="form-input"
                                        placeholder="模板说明"
                                        value={templateDrafts[type]?.description || ''}
                                        onChange={(e) => setTemplateDrafts((prev) => ({
                                            ...prev,
                                            [type]: { ...prev[type], description: e.target.value },
                                        }))}
                                        style={{ minWidth: '180px', height: '26px' }}
                                    />
                                    <button
                                        className="btn btn-sm btn-secondary"
                                        onClick={() => createOpportunityTemplate(type)}
                                    >
                                        保存模板
                                    </button>
                                </div>

                                {Array.isArray(opportunityTemplates[type]) && opportunityTemplates[type].length > 0 && (
                                    <div style={{ marginTop: '8px', fontSize: '10px' }}>
                                        <div style={{ fontWeight: 600, marginBottom: '6px' }}>模板列表</div>
                                        <div style={{ display: 'grid', gap: '6px' }}>
                                            {opportunityTemplates[type].slice(0, 10).map((tpl) => (
                                                <div key={tpl.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 600 }}>{tpl.name}</div>
                                                        <div style={{ color: 'var(--text-muted)' }}>{tpl.description || '-'}</div>
                                                    </div>
                                                    <button className="btn btn-sm btn-primary" onClick={() => applyOpportunityTemplate(type, tpl.id)}>
                                                        应用
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {Array.isArray(opportunityHistory[type]) && opportunityHistory[type].length > 0 && (
                                    <div style={{ marginTop: '8px', fontSize: '10px' }}>
                                        <div style={{ fontWeight: 600, marginBottom: '6px' }}>版本历史</div>
                                        <div style={{ display: 'grid', gap: '6px' }}>
                                            {opportunityHistory[type].slice(0, 10).map((item) => (
                                                <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                                                    <div>
                                                        <div>v{item.version}</div>
                                                        <div style={{ color: 'var(--text-muted)' }}>
                                                            {item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                                                        </div>
                                                    </div>
                                                    <div style={{ color: 'var(--text-muted)' }}>配置快照</div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
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
