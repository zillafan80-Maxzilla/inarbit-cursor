import React, { useEffect, useState } from 'react';
import { configAPI } from '../api/client';

const ConfigCatalog = () => {
    const [exchanges, setExchanges] = useState([]);
    const [pairs, setPairs] = useState([]);
    const [currencies, setCurrencies] = useState([]);
    const [exchangeFilter, setExchangeFilter] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const load = async () => {
        setLoading(true);
        setError('');
        try {
            const [ex, cu] = await Promise.all([
                configAPI.getExchanges(),
                configAPI.getCurrencies(),
            ]);
            const exchangeList = ex?.data || [];
            setExchanges(exchangeList);
            setCurrencies(cu?.data || []);

            const pairResp = await configAPI.getPairs(exchangeFilter || null);
            setPairs(pairResp?.data || []);
        } catch (e) {
            setError(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, [exchangeFilter]);

    const refreshCache = async () => {
        try {
            await configAPI.refreshCache();
            await load();
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">配置目录</h1>
                    <p className="page-subtitle">交易对、基础币种与配置缓存</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button onClick={load} className="btn btn-secondary">🔄 刷新</button>
                    <button onClick={refreshCache} className="btn btn-primary">刷新缓存</button>
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
                    <div className="stats-row" style={{ marginBottom: '16px' }}>
                        <div className="stat-box">
                            <div className="stat-label">交易所</div>
                            <div className="stat-num">{exchanges.length}</div>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">交易对</div>
                            <div className="stat-num">{pairs.length}</div>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">基础币种</div>
                            <div className="stat-num">{currencies.length}</div>
                        </div>
                    </div>

                    <div className="stat-box" style={{ padding: '12px', marginBottom: '12px' }}>
                        <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>交易对列表</h3>
                        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
                            <select value={exchangeFilter} onChange={(e) => setExchangeFilter(e.target.value)} className="form-input" style={{ minWidth: '160px' }}>
                                <option value="">全部交易所</option>
                                {exchanges.map((ex) => (
                                    <option key={ex.id || ex.exchange_id} value={ex.exchange_id}>{ex.exchange_id}</option>
                                ))}
                            </select>
                            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>已加载 {pairs.length} 条</span>
                        </div>
                        {pairs.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无交易对</div>}
                        {pairs.length > 0 && (
                            <div className="data-table-container">
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th>交易对</th>
                                            <th>基础币</th>
                                            <th>计价币</th>
                                            <th>交易所</th>
                                            <th>启用</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {pairs.slice(0, 200).map((p, idx) => (
                                            <tr key={`${p.symbol}-${idx}`}>
                                                <td>{p.symbol}</td>
                                                <td>{p.base_currency || p.base}</td>
                                                <td>{p.quote_currency || p.quote}</td>
                                                <td>{p.exchange_id || '-'}</td>
                                                <td>{p.is_active === false ? '否' : '是'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>

                    <div className="stat-box" style={{ padding: '12px' }}>
                        <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>基础币种</h3>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {currencies.map((c) => (
                                <span key={c} style={{ padding: '4px 8px', borderRadius: '999px', background: 'rgba(0,0,0,0.04)', fontSize: '10px' }}>{c}</span>
                            ))}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default ConfigCatalog;
