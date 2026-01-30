import React, { useEffect, useState } from 'react';
import { decisionAPI, createReconnectingWebSocketWithParams } from '../api/client';

const DecisionConsole = () => {
    const [constraints, setConstraints] = useState(null);
    const [autoConstraints, setAutoConstraints] = useState(null);
    const [effectiveConstraints, setEffectiveConstraints] = useState(null);
    const [decisions, setDecisions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [filters, setFilters] = useState({
        exchange: '',
        symbol: '',
        strategy: '',
        minProfitRate: '',
        minConfidence: ''
    });

    const [form, setForm] = useState({
        max_exposure_per_symbol: '',
        max_total_exposure: '',
        min_profit_rate: '',
        max_positions: '',
        blacklist_symbols: '',
        whitelist_symbols: '',
        max_drawdown_per_symbol: '',
        liquidity_score_min: '',
        max_spread_rate: '',
        max_data_age_ms: '',
        min_confidence: '',
        max_abs_funding_rate: '',
    });

    const load = async () => {
        setLoading(true);
        setError('');
        try {
            const [c, a, e, d] = await Promise.all([
                decisionAPI.getConstraints(),
                decisionAPI.getAutoConstraints(),
                decisionAPI.getEffectiveConstraints(),
                decisionAPI.listDecisions({ limit: 20 }),
            ]);
            setConstraints(c || {});
            setAutoConstraints(a || {});
            setEffectiveConstraints(e || {});
            if (Array.isArray(d?.decisions)) {
                setDecisions(d.decisions);
            }
            setForm((prev) => ({
                ...prev,
                ...Object.fromEntries(Object.entries(c || {}).map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : String(v)])),
            }));
        } catch (err) {
            setError(String(err?.message || err));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    useEffect(() => {
        const socket = createReconnectingWebSocketWithParams(
            'decisions',
            { interval: '1', limit: '20' },
            (payload) => {
                if (!payload || payload.type !== 'decisions') return;
                if (Array.isArray(payload.data)) {
                    setDecisions(payload.data);
                }
            },
            3000
        );
        return () => socket.close();
    }, []);

    const parsePayload = () => {
        const num = (v) => (v === '' ? undefined : Number(v));
        const intVal = (v) => (v === '' ? undefined : parseInt(v, 10));
        const listVal = (v) => {
            if (!v) return undefined;
            return String(v).split(',').map((s) => s.trim()).filter(Boolean);
        };
        return {
            max_exposure_per_symbol: num(form.max_exposure_per_symbol),
            max_total_exposure: num(form.max_total_exposure),
            min_profit_rate: num(form.min_profit_rate),
            max_positions: intVal(form.max_positions),
            blacklist_symbols: listVal(form.blacklist_symbols),
            whitelist_symbols: listVal(form.whitelist_symbols),
            max_drawdown_per_symbol: num(form.max_drawdown_per_symbol),
            liquidity_score_min: num(form.liquidity_score_min),
            max_spread_rate: num(form.max_spread_rate),
            max_data_age_ms: intVal(form.max_data_age_ms),
            min_confidence: num(form.min_confidence),
            max_abs_funding_rate: num(form.max_abs_funding_rate),
        };
    };

    const updateConstraints = async () => {
        try {
            const payload = parsePayload();
            await decisionAPI.updateConstraints(payload);
            await load();
            alert('约束已更新');
        } catch (err) {
            alert(String(err?.message || err));
        }
    };

    const clearDecisions = async () => {
        if (!confirm('确认清空当前决策列表？')) return;
        try {
            await decisionAPI.clearDecisions();
            await load();
        } catch (err) {
            alert(String(err?.message || err));
        }
    };

    const constraintLabels = {
        max_exposure_per_symbol: '单币最大敞口',
        max_total_exposure: '总敞口上限',
        min_profit_rate: '最低收益率',
        max_positions: '最大持仓数',
        blacklist_symbols: '黑名单币种',
        whitelist_symbols: '白名单币种',
        max_drawdown_per_symbol: '单币最大回撤',
        liquidity_score_min: '最低流动性评分',
        max_spread_rate: '最大价差比例',
        max_data_age_ms: '最大数据延迟(毫秒)',
        min_confidence: '最低置信度',
        max_abs_funding_rate: '最大资金费率绝对值',
    };

    const strategyLabelMap = {
        triangular: '三角套利',
        cashcarry: '期现套利',
        cash_carry: '期现套利',
        funding_rate: '期现套利',
        funding: '资金费率套利',
        graph: '图搜索套利',
        grid: '网格交易',
        pair: '配对交易',
        'bellman-ford': '贝尔曼-福特',
        'z-score': 'Z 分数',
        zscore: 'Z 分数',
        stat_arb: '统计套利',
        market_making: '做市',
    };

    const directionLabelMap = {
        buy: '买入',
        sell: '卖出',
        long: '做多',
        short: '做空',
        bid: '买入',
        ask: '卖出',
        open_long: '开多',
        open_short: '开空',
        close_long: '平多',
        close_short: '平空',
    };

    const hasChinese = (value) => /[\u4e00-\u9fa5]/.test(String(value || ''));
    const normalizeKey = (value) => String(value || '').trim().toLowerCase();

    const getStrategyLabel = (value) => {
        if (!value) return '—';
        if (hasChinese(value)) return String(value);
        const key = normalizeKey(value);
        return strategyLabelMap[key]
            || strategyLabelMap[key.replace(/\s+/g, '_')]
            || strategyLabelMap[key.replace(/-/g, '_')]
            || '未知策略';
    };

    const getDirectionLabel = (value) => {
        if (!value) return '—';
        if (hasChinese(value)) return String(value);
        const key = normalizeKey(value);
        return directionLabelMap[key]
            || directionLabelMap[key.replace(/\s+/g, '_')]
            || directionLabelMap[key.replace(/-/g, '_')]
            || '未知方向';
    };

    const filteredDecisions = decisions.filter((d) => {
        const exchange = String(d.exchange || d.exchange_id || '').toLowerCase();
        const symbol = String(d.symbol || '').toLowerCase();
        const strategy = String(d.strategyType || d.strategy_type || '').toLowerCase();
        const profitRate = Number(d.expectedProfitRate || d.expected_profit_rate || 0);
        const confidence = Number(d.confidence || 0);

        const matchExchange = !filters.exchange || exchange.includes(filters.exchange.toLowerCase());
        const matchSymbol = !filters.symbol || symbol.includes(filters.symbol.toLowerCase());
        const matchStrategy = !filters.strategy || strategy.includes(filters.strategy.toLowerCase());
        const matchProfit = !filters.minProfitRate || profitRate >= Number(filters.minProfitRate);
        const matchConfidence = !filters.minConfidence || confidence >= Number(filters.minConfidence);

        return matchExchange && matchSymbol && matchStrategy && matchProfit && matchConfidence;
    });

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">决策管理</h1>
                    <p className="page-subtitle">避险约束与实时决策列表</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button onClick={load} className="btn btn-secondary">🔄 刷新</button>
                    <button onClick={clearDecisions} className="btn btn-danger">清空决策</button>
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
                    <div className="stat-box" style={{ padding: '12px', marginBottom: '12px' }}>
                        <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>避险约束配置</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '10px' }}>
                            {Object.keys(form).map((key) => (
                                <div key={key}>
                                    <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>{constraintLabels[key] || key}</label>
                                    <input
                                        className="form-input"
                                        value={form[key]}
                                        onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
                                        placeholder={key.includes('symbols') ? '用逗号分隔' : ''}
                                    />
                                </div>
                            ))}
                        </div>
                        <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'flex-end' }}>
                            <button className="btn btn-primary" onClick={updateConstraints}>保存约束</button>
                        </div>
                    </div>

                    <div className="stats-row" style={{ marginBottom: '12px' }}>
                        <div className="stat-box">
                            <div className="stat-label">当前约束</div>
                            <pre style={{ fontSize: '10px', marginTop: '8px', whiteSpace: 'pre-wrap' }}>{JSON.stringify(constraints || {}, null, 2)}</pre>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">自动约束</div>
                            <pre style={{ fontSize: '10px', marginTop: '8px', whiteSpace: 'pre-wrap' }}>{JSON.stringify(autoConstraints || {}, null, 2)}</pre>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">生效约束</div>
                            <pre style={{ fontSize: '10px', marginTop: '8px', whiteSpace: 'pre-wrap' }}>{JSON.stringify(effectiveConstraints || {}, null, 2)}</pre>
                        </div>
                    </div>

                    <div className="stat-box" style={{ padding: '12px' }}>
                        <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>实时决策列表</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '8px', marginBottom: '10px' }}>
                            <input
                                className="form-input"
                                placeholder="交易所过滤"
                                value={filters.exchange}
                                onChange={(e) => setFilters((prev) => ({ ...prev, exchange: e.target.value }))}
                            />
                            <input
                                className="form-input"
                                placeholder="交易对过滤"
                                value={filters.symbol}
                                onChange={(e) => setFilters((prev) => ({ ...prev, symbol: e.target.value }))}
                            />
                            <input
                                className="form-input"
                                placeholder="策略过滤"
                                value={filters.strategy}
                                onChange={(e) => setFilters((prev) => ({ ...prev, strategy: e.target.value }))}
                            />
                            <input
                                className="form-input"
                                type="number"
                                step="0.0001"
                                placeholder="最小收益率"
                                value={filters.minProfitRate}
                                onChange={(e) => setFilters((prev) => ({ ...prev, minProfitRate: e.target.value }))}
                            />
                            <input
                                className="form-input"
                                type="number"
                                step="0.01"
                                placeholder="最小置信度"
                                value={filters.minConfidence}
                                onChange={(e) => setFilters((prev) => ({ ...prev, minConfidence: e.target.value }))}
                            />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '10px', color: 'var(--text-muted)' }}>
                            <span>共 {decisions.length} 条，筛选后 {filteredDecisions.length} 条</span>
                            <button
                                className="btn btn-secondary"
                                onClick={() => setFilters({ exchange: '', symbol: '', strategy: '', minProfitRate: '', minConfidence: '' })}
                            >
                                清空筛选
                            </button>
                        </div>
                        {decisions.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无决策</div>}
                        {decisions.length > 0 && (
                            <div className="data-table-container">
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th>策略</th>
                                            <th>交易所</th>
                                            <th>交易对</th>
                                            <th>方向</th>
                                            <th>期望收益率</th>
                                            <th>风险分</th>
                                            <th>置信度</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredDecisions.map((d, idx) => (
                                            <tr key={`${d.symbol}-${idx}`}>
                                                <td>{getStrategyLabel(d.strategyType || d.strategy_type)}</td>
                                                <td>{d.exchange || d.exchange_id}</td>
                                                <td>{d.symbol}</td>
                                                <td>{getDirectionLabel(d.direction)}</td>
                                                <td>{(Number(d.expectedProfitRate || d.expected_profit_rate || 0) * 100).toFixed(3)}%</td>
                                                <td>{Number(d.riskScore || d.risk_score || 0).toFixed(3)}</td>
                                                <td>{Number(d.confidence || 0).toFixed(3)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};

export default DecisionConsole;
