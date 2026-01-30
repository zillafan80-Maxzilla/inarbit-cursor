import React, { useEffect, useState } from 'react';
import { systemAPI } from '../api/client';

const SystemOverview = () => {
    const [status, setStatus] = useState(null);
    const [metrics, setMetrics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const load = async () => {
        setLoading(true);
        setError('');
        try {
            const [s, m] = await Promise.all([systemAPI.status(), systemAPI.metrics()]);
            setStatus(s?.data || s);
            setMetrics(m?.data || m);
        } catch (e) {
            setError(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">系统概览</h1>
                    <p className="page-subtitle">系统状态与关键指标（仅管理员可见）</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button onClick={load} className="btn btn-secondary">🔄 刷新</button>
                </div>
            </div>

            {loading && (
                <div className="loading">
                    <div className="loading-spinner"></div>
                </div>
            )}

            {!loading && error && (
                <div className="stat-box" style={{ padding: '12px', color: 'var(--color-danger)' }}>
                    {error}
                </div>
            )}

            {!loading && !error && (
                <>
                    <div className="stats-row" style={{ marginBottom: '16px' }}>
                        <div className="stat-box">
                            <div className="stat-label">用户数</div>
                            <div className="stat-num">{status?.users ?? 0}</div>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">策略数</div>
                            <div className="stat-num">{status?.strategies ?? 0}</div>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">交易所</div>
                            <div className="stat-num">{status?.exchanges ?? 0}</div>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">订单数</div>
                            <div className="stat-num">{status?.orders ?? 0}</div>
                        </div>
                        <div className="stat-box">
                            <div className="stat-label">收益记录</div>
                            <div className="stat-num">{status?.pnlRecords ?? 0}</div>
                        </div>
                    </div>

                    <div className="stat-box" style={{ padding: '12px', marginBottom: '12px' }}>
                        <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>实时指标</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '10px' }}>
                            <div>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>三角机会</div>
                                <div style={{ fontSize: '12px', fontWeight: 600 }}>{metrics?.opportunities?.triangular ?? 0}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>期现机会</div>
                                <div style={{ fontSize: '12px', fontWeight: 600 }}>{metrics?.opportunities?.cashcarry ?? 0}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>决策数量</div>
                                <div style={{ fontSize: '12px', fontWeight: 600 }}>{metrics?.decisions ?? 0}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>行情数据</div>
                                <div style={{ fontSize: '12px', fontWeight: 600 }}>{metrics?.market_data?.symbols_spot ?? 0} / {metrics?.market_data?.symbols_futures ?? 0}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>市场状态</div>
                                <div style={{ fontSize: '12px', fontWeight: 600 }}>{metrics?.market_regime?.regime || '-'}</div>
                            </div>
                        </div>
                    </div>

                    <div className="stat-box" style={{ padding: '12px' }}>
                        <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>指标详情</h3>
                        <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '360px', overflow: 'auto' }}>
                            {JSON.stringify(metrics || {}, null, 2)}
                        </pre>
                    </div>
                </>
            )}
        </div>
    );
};

export default SystemOverview;
