import React, { useEffect, useState } from 'react';
import { arbitrageAPI, createReconnectingWebSocketWithParams } from '../api/client';

const ArbitrageMonitor = () => {
    const [type, setType] = useState('triangular');
    const [limit, setLimit] = useState(50);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [wsKey, setWsKey] = useState(0);
    const [filters, setFilters] = useState({
        symbol: '',
        exchange: '',
        minProfitRate: ''
    });

    const load = async () => {
        setLoading(true);
        setError('');
        try {
            const resp = await arbitrageAPI.listOpportunities({ type, limit });
            setItems(resp?.items || []);
        } catch (e) {
            setError(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
        const socket = createReconnectingWebSocketWithParams(
            'opportunities',
            {
                type,
                limit: String(limit),
                interval: '1',
            },
            (payload) => {
                if (!payload || payload.type !== 'opportunities') return;
                setItems(Array.isArray(payload.data) ? payload.data : []);
                setLoading(false);
            },
            3000
        );
        return () => socket.close();
    }, [type, limit, wsKey]);

    const clearOpportunities = async () => {
        if (!confirm('确认清空当前套利机会缓存？')) return;
        try {
            await arbitrageAPI.clearOpportunities({ type });
            setItems([]);
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    const filteredItems = items.filter((item) => {
        const symbol = String(item.symbol || item.base_symbol || '').toLowerCase();
        const exchangeRaw = String(item.exchange_id || item.exchange || '');
        const exchange = exchangeRaw.toLowerCase();
        const profitRate = Number(item.profit_rate || 0);

        const symbolQuery = filters.symbol.toLowerCase();
        const exchangeQuery = filters.exchange.toLowerCase();

        const matchSymbol = !filters.symbol || symbol.includes(symbolQuery);
        const matchExchange = !filters.exchange || exchange.includes(exchangeQuery);
        const matchProfit = !filters.minProfitRate || profitRate >= Number(filters.minProfitRate);

        return matchSymbol && matchExchange && matchProfit;
    });

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">套利机会</h1>
                    <p className="page-subtitle">实时套利机会流（缓存总线，仅三角/期现）</p>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <select value={type} onChange={(e) => setType(e.target.value)} className="form-input" style={{ minWidth: '140px' }}>
                        <option value="triangular">🔺 三角套利</option>
                        <option value="cashcarry">💹 期现套利</option>
                    </select>
                    <input
                        type="number"
                        value={limit}
                        onChange={(e) => setLimit(Number(e.target.value))}
                        className="form-input"
                        style={{ width: '90px' }}
                    />
                    <button
                        onClick={() => setWsKey((v) => v + 1)}
                        className="btn btn-secondary"
                        style={{ minWidth: '88px', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                        🔄 刷新
                    </button>
                    <button
                        onClick={clearOpportunities}
                        className="btn btn-danger"
                        style={{ minWidth: '96px', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                        清空机会
                    </button>
                </div>
            </div>

            <div style={{
                marginBottom: '12px',
                padding: '10px 12px',
                background: 'rgba(38, 139, 210, 0.08)',
                borderRadius: '8px',
                fontSize: '10px',
                color: 'var(--text-secondary)'
            }}>
                提示：套利机会流目前只支持“三角套利”和“期现套利”。网格交易不会输出套利机会到此页面。
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
                <div className="stat-box" style={{ padding: '12px' }}>
                    <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>机会列表</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '8px', marginBottom: '10px' }}>
                        <input
                            className="form-input"
                            placeholder="交易对过滤"
                            value={filters.symbol}
                            onChange={(e) => setFilters((prev) => ({ ...prev, symbol: e.target.value }))}
                        />
                        <input
                            className="form-input"
                            placeholder="交易所过滤"
                            value={filters.exchange}
                            onChange={(e) => setFilters((prev) => ({ ...prev, exchange: e.target.value }))}
                        />
                        <input
                            className="form-input"
                            type="number"
                            step="0.0001"
                            placeholder="最小收益率"
                            value={filters.minProfitRate}
                            onChange={(e) => setFilters((prev) => ({ ...prev, minProfitRate: e.target.value }))}
                        />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '10px', color: 'var(--text-muted)' }}>
                        <span>共 {items.length} 条，筛选后 {filteredItems.length} 条</span>
                        <button
                            className="btn btn-secondary"
                            onClick={() => setFilters({ symbol: '', exchange: '', minProfitRate: '' })}
                        >
                            清空筛选
                        </button>
                    </div>
                    {items.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无机会</div>}
                    {items.length > 0 && (
                        <div className="data-table-container">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>评分</th>
                                        <th>交易对</th>
                                        <th>路径/腿</th>
                                        <th>收益率</th>
                                        <th>交易所</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredItems.map((item, idx) => (
                                        <tr key={`${idx}-${item.score || ''}`}>
                                            <td>{Number(item.score || 0).toFixed(6)}</td>
                                            <td>{item.symbol || item.base_symbol || '-'}</td>
                                            <td style={{ fontFamily: 'monospace' }}>{item.path || item.legs || item.route || '-'}</td>
                                            <td>{item.profit_rate ? `${(Number(item.profit_rate) * 100).toFixed(4)}%` : '-'}</td>
                                            <td>{item.exchange_id || item.exchange || '-'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                    <pre style={{ fontSize: '10px', marginTop: '12px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '280px', overflow: 'auto' }}>
                        {JSON.stringify(filteredItems.slice(0, 20), null, 2)}
                    </pre>
                </div>
            )}
        </div>
    );
};

export default ArbitrageMonitor;
