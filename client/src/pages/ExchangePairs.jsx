import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { exchangeV2API } from '../api/client';

const ExchangePairs = () => {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [exchanges, setExchanges] = useState([]);
    const [exchangeId, setExchangeId] = useState('');
    const [pairs, setPairs] = useState([]);
    const [stats, setStats] = useState(null);
    const [enabledOnly, setEnabledOnly] = useState(false);
    const [search, setSearch] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [bulkUpdating, setBulkUpdating] = useState(false);
    const [selected, setSelected] = useState(() => new Set());

    const exchangeIdFromUrl = useMemo(() => searchParams.get('exchange_id') || '', [searchParams]);

    const loadExchanges = async () => {
        const res = await exchangeV2API.list();
        const list = res?.data || [];
        setExchanges(list);
    };

    const loadPairs = async () => {
        if (!exchangeId) return;
        setLoading(true);
        setError('');
        try {
            const [pairsResp, statsResp] = await Promise.all([
                exchangeV2API.getPairs(exchangeId, { enabled_only: enabledOnly ? 'true' : 'false' }),
                exchangeV2API.stats(exchangeId),
            ]);
            setPairs(pairsResp?.pairs || []);
            setStats(statsResp || null);
        } catch (e) {
            setError(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadExchanges();
    }, []);

    useEffect(() => {
        if (!exchanges.length) return;
        if (exchangeIdFromUrl && exchanges.some((ex) => ex.id === exchangeIdFromUrl)) {
            setExchangeId(exchangeIdFromUrl);
            return;
        }
        if (!exchangeId || !exchanges.some((ex) => ex.id === exchangeId)) {
            setExchangeId(exchanges[0].id);
        }
    }, [exchangeIdFromUrl, exchanges]);

    useEffect(() => {
        loadPairs();
    }, [exchangeId, enabledOnly]);

    const filteredPairs = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return pairs;
        return (pairs || []).filter((p) => String(p.symbol || '').toLowerCase().includes(q));
    }, [pairs, search]);

    useEffect(() => {
        setSelected(new Set());
    }, [exchangeId, search, enabledOnly]);

    const selectedExchange = useMemo(() => {
        return exchanges.find((ex) => ex.id === exchangeId) || null;
    }, [exchanges, exchangeId]);

    const togglePair = async (pairId, current) => {
        try {
            await exchangeV2API.togglePair(exchangeId, pairId, { trading_pair_id: pairId, is_enabled: !current });
            await loadPairs();
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    const bulkToggle = async (targetEnabled) => {
        if (!exchangeId) return;
        const selectedIds = Array.from(selected);
        const scope = selectedIds.length
            ? filteredPairs.filter((p) => selectedIds.includes(p.pair_id))
            : filteredPairs;
        const items = scope.filter((p) => p.is_enabled !== targetEnabled);
        if (!items.length) return;
        const actionLabel = targetEnabled ? '启用' : '禁用';
        if (!confirm(`确认批量${actionLabel} ${items.length} 个交易对？`)) {
            return;
        }
        setBulkUpdating(true);
        try {
            await Promise.all(
                items.map((p) => exchangeV2API.togglePair(exchangeId, p.pair_id, {
                    trading_pair_id: p.pair_id,
                    is_enabled: targetEnabled,
                }))
            );
            await loadPairs();
        } catch (e) {
            alert(String(e?.message || e));
        }
        setBulkUpdating(false);
    };

    const toggleSelected = (pairId) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(pairId)) {
                next.delete(pairId);
            } else {
                next.add(pairId);
            }
            return next;
        });
    };

    const toggleAll = () => {
        const allIds = filteredPairs.map((p) => p.pair_id);
        setSelected((prev) => {
            const next = new Set(prev);
            const allSelected = allIds.every((id) => next.has(id));
            if (allSelected) {
                allIds.forEach((id) => next.delete(id));
            } else {
                allIds.forEach((id) => next.add(id));
            }
            return next;
        });
    };

    const exportCsv = () => {
        const selectedIds = Array.from(selected);
        const scope = selectedIds.length
            ? filteredPairs.filter((p) => selectedIds.includes(p.pair_id))
            : filteredPairs;
        if (!scope.length) return;
        const header = ['交易对', '基础币', '计价币', '挂单费率', '吃单费率', '是否启用'];
        const rows = scope.map((p) => [
            p.symbol,
            p.base_currency,
            p.quote_currency,
            p.maker_fee ?? '',
            p.taker_fee ?? '',
            p.is_enabled ? '启用' : '禁用',
        ]);
        const csv = [header, ...rows]
            .map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
            .join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `交易对导出_${exchangeId ? '所选交易所' : '全部'}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">交易对管理</h1>
                    <p className="page-subtitle">按交易所启用/禁用交易对</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button
                        onClick={() => bulkToggle(true)}
                        className="btn btn-secondary"
                        disabled={bulkUpdating || filteredPairs.length === 0}
                    >
                        ✅ 批量启用
                    </button>
                    <button
                        onClick={() => bulkToggle(false)}
                        className="btn btn-secondary"
                        disabled={bulkUpdating || filteredPairs.length === 0}
                    >
                        🚫 批量禁用
                    </button>
                    <button
                        onClick={exportCsv}
                        className="btn btn-secondary"
                        disabled={filteredPairs.length === 0}
                    >
                        📥 导出
                    </button>
                    <button
                        onClick={async () => {
                            await loadExchanges();
                            await loadPairs();
                        }}
                        className="btn btn-secondary"
                    >
                        🔄 刷新
                    </button>
                </div>
            </div>

            <div className="stat-box" style={{ padding: '12px', marginBottom: '12px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '10px' }}>
                    <div>
                        <label className="form-label">交易所</label>
                        <select className="form-input" value={exchangeId} onChange={(e) => setExchangeId(e.target.value)}>
                            {exchanges.map((ex) => (
                                <option key={ex.id} value={ex.id}>{ex.display_name || ex.exchange_id}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="form-label">筛选</label>
                        <input className="form-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="输入交易对" />
                    </div>
                    <div>
                        <label className="form-label">状态</label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--text-muted)', marginTop: '6px' }}>
                            <input type="checkbox" checked={enabledOnly} onChange={(e) => setEnabledOnly(e.target.checked)} />
                            仅显示启用
                        </label>
                    </div>
                    <div>
                        <label className="form-label">统计</label>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '6px' }}>
                            {stats ? `总对数:${stats.total_pairs || stats.total || 0} / 启用:${stats.enabled_pairs || stats.enabled || 0}` : '—'}
                        </div>
                    </div>
                </div>
                {selectedExchange && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '10px' }}>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                            当前交易所：{selectedExchange.display_name || selectedExchange.exchange_id}
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '6px' }}>
                                已选 {selected.size}
                                {selected.size > 0 && (
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        style={{ marginLeft: '8px' }}
                                        onClick={() => setSelected(new Set())}
                                    >
                                        清空
                                    </button>
                                )}
                            </div>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => navigate(`/live-assets?exchange_id=${exchangeId}`)}
                            >
                                🏦 资产
                            </button>
                        </div>
                    </div>
                )}
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
                <div className="data-table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th style={{ width: '46px' }}>
                                    <input
                                        type="checkbox"
                                        onChange={toggleAll}
                                        checked={filteredPairs.length > 0 && filteredPairs.every((p) => selected.has(p.pair_id))}
                                    />
                                </th>
                                <th>交易对</th>
                                <th>基础币</th>
                                <th>计价币</th>
                                <th>挂单费率</th>
                                <th>吃单费率</th>
                                <th>状态</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredPairs.map((p) => (
                                <tr key={p.pair_id}>
                                    <td>
                                        <input
                                            type="checkbox"
                                            checked={selected.has(p.pair_id)}
                                            onChange={() => toggleSelected(p.pair_id)}
                                        />
                                    </td>
                                    <td>{p.symbol}</td>
                                    <td>{p.base_currency}</td>
                                    <td>{p.quote_currency}</td>
                                    <td>{p.maker_fee ?? '-'}</td>
                                    <td>{p.taker_fee ?? '-'}</td>
                                    <td>
                                        <span className={`table-badge ${p.is_enabled ? 'success' : 'neutral'}`}>
                                            {p.is_enabled ? '● 已启用' : '○ 已禁用'}
                                        </span>
                                    </td>
                                    <td>
                                        <button className="btn btn-secondary btn-sm" onClick={() => togglePair(p.pair_id, p.is_enabled)}>
                                            {p.is_enabled ? '禁用' : '启用'}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                            {filteredPairs.length === 0 && (
                                <tr>
                                    <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '10px' }}>暂无交易对</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

export default ExchangePairs;
