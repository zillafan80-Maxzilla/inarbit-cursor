/**
 * 交易所管理页面
 * 灰绿色主题重构版 - 表格列表风格
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useExchanges } from '../api/hooks';
import { exchangeV2API } from '../api/client';

// 支持的交易所列表
const SUPPORTED_EXCHANGES = [
    { id: 'binance', name: 'Binance', fullName: 'Binance', icon: '🟡', color: '#F0B90B', setupSupported: true },
    { id: 'okx', name: 'OKX', fullName: 'OKX', icon: '⚪', color: '#121212', setupSupported: false },
    { id: 'bybit', name: 'Bybit', fullName: 'Bybit', icon: '🟠', color: '#F7A600', setupSupported: false },
    { id: 'gate', name: 'Gate.io', fullName: 'Gate.io', icon: '🔵', color: '#2354E6', setupSupported: false },
    { id: 'bitget', name: 'Bitget', fullName: 'Bitget', icon: '🟢', color: '#00C853', setupSupported: false },
    { id: 'mexc', name: 'MEXC', fullName: 'MEXC', icon: '🔷', color: '#1C9AEA', setupSupported: false }
];

const ExchangeManagement = () => {
    const navigate = useNavigate();
    const { exchanges, loading, refresh } = useExchanges();
    const [showAddModal, setShowAddModal] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [statsTarget, setStatsTarget] = useState(null);
    const [statsLoading, setStatsLoading] = useState(false);
    const [statsData, setStatsData] = useState(null);
    const [statsError, setStatsError] = useState('');

    const handleDelete = (exchange) => {
        setDeleteTarget(exchange);
    };

    const handleStats = async (exchange) => {
        setStatsTarget(exchange);
        setStatsLoading(true);
        setStatsError('');
        try {
            const data = await exchangeV2API.stats(exchange.id);
            setStatsData(data);
        } catch (err) {
            setStatsError(String(err?.message || err));
            setStatsData(null);
        }
        setStatsLoading(false);
    };

    const getExchangeInfo = (id) => {
        return SUPPORTED_EXCHANGES.find(e => e.id === id) || { icon: '❓', name: '未知交易所', fullName: '未知交易所', color: '#999' };
    };

    // 添加交易所模态框
    const AddExchangeModal = ({ onClose }) => {
        const [form, setForm] = useState({
            exchange_type: 'binance',
            display_name: 'Binance',
            api_key: '',
            api_secret: '',
            passphrase: ''
        });
        const [saving, setSaving] = useState(false);

        const handleSubmit = async (e) => {
            e.preventDefault();
            if (!form.api_key || !form.api_secret) {
                alert('请填写接口密钥和密钥密码');
                return;
            }
            const selected = getExchangeInfo(form.exchange_type);
            if (!selected.setupSupported) {
                alert('当前仅支持 Binance 的一键接入');
                return;
            }
            setSaving(true);
            try {
                const result = await exchangeV2API.setup({
                    exchange_type: form.exchange_type,
                    api_key: form.api_key,
                    api_secret: form.api_secret,
                    passphrase: form.passphrase || undefined,
                    display_name: form.display_name
                });
                await refresh();
                onClose();
                if (result?.message) {
                    alert(result.message);
                }
            } catch (err) {
                alert(`添加失败: ${err.message}`);
            }
            setSaving(false);
        };

        const selectedExchange = getExchangeInfo(form.exchange_type);

        return (
            <div style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1100,
                backdropFilter: 'blur(4px)'
            }}>
                <div className="card" style={{ width: '90%', maxWidth: '500px' }}>
                    <div className="card-header">
                        <span className="card-title">➕ 添加交易所</span>
                        <button onClick={onClose} className="btn btn-icon btn-secondary">×</button>
                    </div>
                    <form onSubmit={handleSubmit}>
                        <div className="card-body">
                            {/* 交易所选择 */}
                            <div className="form-group">
                                <label className="form-label">选择交易所</label>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                                    {SUPPORTED_EXCHANGES.map(ex => (
                                        <button
                                            key={ex.id}
                                            type="button"
                                            onClick={() => setForm({
                                                ...form,
                                                exchange_type: ex.id,
                                                display_name: ex.fullName || ex.name
                                            })}
                                            className={`btn ${form.exchange_type === ex.id ? 'btn-primary' : 'btn-secondary'}`}
                                            aria-disabled={!ex.setupSupported}
                                            data-disabled={!ex.setupSupported}
                                            style={{
                                                flexDirection: 'column',
                                                padding: '12px 8px',
                                                gap: '4px',
                                                opacity: ex.setupSupported ? 1 : 0.5,
                                                cursor: 'pointer'
                                            }}
                                        >
                                            <span style={{ fontSize: '20px' }}>{ex.icon}</span>
                                            <span style={{ fontSize: '11px' }}>{ex.fullName || ex.name}</span>
                                            {!ex.setupSupported && (
                                                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>未接入</span>
                                            )}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* 显示名称 */}
                            <div className="form-group">
                                <label className="form-label">显示名称</label>
                                <input
                                    type="text"
                                    value={form.display_name}
                                    onChange={e => setForm({ ...form, display_name: e.target.value })}
                                    placeholder="交易所显示名称"
                                />
                            </div>

                            {/* API Key */}
                            <div className="form-group">
                                <label className="form-label">接口密钥</label>
                                <input
                                    type="text"
                                    value={form.api_key}
                                    onChange={e => setForm({ ...form, api_key: e.target.value })}
                                    placeholder="输入接口密钥"
                                    required
                                />
                            </div>

                            {/* API Secret */}
                            <div className="form-group">
                                <label className="form-label">接口密钥密码</label>
                                <input
                                    type="password"
                                    value={form.api_secret}
                                    onChange={e => setForm({ ...form, api_secret: e.target.value })}
                                    placeholder="输入接口密钥密码"
                                    required
                                />
                            </div>

                            {/* Passphrase (可选) */}
                            <div className="form-group">
                                <label className="form-label">资金密码（可选）</label>
                                <input
                                    type="password"
                                    value={form.passphrase}
                                    onChange={e => setForm({ ...form, passphrase: e.target.value })}
                                    placeholder="如交易所要求，请填写资金密码"
                                />
                                <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                                    OKX/部分交易所需要此字段，Binance 可留空。
                                </div>
                            </div>

                            {/* 安全提示 */}
                            <div style={{
                                padding: '12px',
                                background: 'rgba(253, 203, 110, 0.1)',
                                borderRadius: 'var(--radius-md)',
                                fontSize: '12px',
                                color: 'var(--text-secondary)'
                            }}>
                                ⚠️ 请确保接口密钥仅开启 <strong>现货交易</strong> 和 <strong>读取</strong> 权限，切勿开启提现权限。
                            </div>
                            <div style={{
                                marginTop: '8px',
                                fontSize: '11px',
                                color: 'var(--text-muted)'
                            }}>
                                当前仅支持 Binance 一键接入，其他交易所将逐步开放。
                            </div>
                        </div>
                        <div className="card-footer" style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                            <button type="button" onClick={onClose} className="btn btn-secondary">取消</button>
                            <button type="submit" disabled={saving} className="btn btn-primary">
                                {saving ? '保存中...' : `添加 ${selectedExchange.fullName || selectedExchange.name}`}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        );
    };

    const DeleteExchangeModal = ({ exchange, onClose }) => {
        const [mode, setMode] = useState('soft');
        const [confirmCode, setConfirmCode] = useState('');
        const [requiredCode, setRequiredCode] = useState('');
        const [saving, setSaving] = useState(false);
        const [error, setError] = useState('');

        const handleSubmit = async () => {
            setSaving(true);
            setError('');
            try {
                await exchangeV2API.deleteExchange(exchange.id, {
                    mode,
                    confirm_code: mode === 'hard' ? (confirmCode || undefined) : undefined,
                });
                await refresh();
                onClose();
            } catch (err) {
                const msg = err?.message || String(err);
                setError(msg);
                const match = msg.match(/confirm_code='([A-Z0-9]+)'/);
                if (match) {
                    setRequiredCode(match[1]);
                }
            }
            setSaving(false);
        };

        const info = getExchangeInfo(exchange.exchange_id);

        return (
            <div style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1100,
                backdropFilter: 'blur(4px)'
            }}>
                <div className="card" style={{ width: '90%', maxWidth: '520px' }}>
                    <div className="card-header">
                        <span className="card-title">🗑 删除交易所</span>
                        <button onClick={onClose} className="btn btn-icon btn-secondary">×</button>
                    </div>
                    <div className="card-body">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                            <div className="table-avatar" style={{
                                background: `linear-gradient(135deg, ${info.color}40, ${info.color}80)`
                            }}>
                                {info.icon}
                            </div>
                            <div>
                                <div style={{ fontWeight: 600 }}>{info.name}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{exchange.display_name || exchange.exchange_id}</div>
                            </div>
                        </div>

                        <div className="form-group">
                            <label className="form-label">删除模式</label>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                                    <input
                                        type="radio"
                                        name="delete-mode"
                                        value="soft"
                                        checked={mode === 'soft'}
                                        onChange={() => setMode('soft')}
                                    />
                                    软删除（保留历史数据）
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                                    <input
                                        type="radio"
                                        name="delete-mode"
                                        value="hard"
                                        checked={mode === 'hard'}
                                        onChange={() => setMode('hard')}
                                    />
                                    硬删除（永久清理）
                                </label>
                            </div>
                        </div>

                        {mode === 'hard' && (
                            <div className="form-group">
                                <label className="form-label">确认码</label>
                                <input
                                    type="text"
                                    value={confirmCode}
                                    onChange={e => setConfirmCode(e.target.value.toUpperCase())}
                                    placeholder="输入确认码"
                                />
                                {requiredCode && (
                                    <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--text-muted)' }}>
                                        需要确认码：<strong>{requiredCode}</strong>
                                    </div>
                                )}
                            </div>
                        )}

                        {error && (
                            <div style={{
                                marginTop: '8px',
                                padding: '8px',
                                borderRadius: '6px',
                                background: 'rgba(220, 50, 47, 0.08)',
                                color: 'var(--color-danger)',
                                fontSize: '11px'
                            }}>
                                {error}
                            </div>
                        )}

                        <div style={{
                            marginTop: '10px',
                            fontSize: '11px',
                            color: 'var(--text-muted)'
                        }}>
                            软删除会停用该交易所并保留历史订单与收益数据；硬删除会彻底清理相关数据，请谨慎操作。
                        </div>
                    </div>
                    <div className="card-footer" style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                        <button type="button" onClick={onClose} className="btn btn-secondary">取消</button>
                        <button type="button" onClick={handleSubmit} disabled={saving} className="btn btn-danger">
                            {saving ? '处理中...' : '确认删除'}
                        </button>
                    </div>
                </div>
            </div>
        );
    };

    const ExchangeStatsModal = ({ exchange, onClose }) => {
        const info = getExchangeInfo(exchange.exchange_id);
        const data = statsData || {};
        return (
            <div style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1100,
                backdropFilter: 'blur(4px)'
            }}>
                <div className="card" style={{ width: '90%', maxWidth: '520px' }}>
                    <div className="card-header">
                        <span className="card-title">📊 交易所统计</span>
                        <button onClick={onClose} className="btn btn-icon btn-secondary">×</button>
                    </div>
                    <div className="card-body">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                            <div className="table-avatar" style={{
                                background: `linear-gradient(135deg, ${info.color}40, ${info.color}80)`
                            }}>
                                {info.icon}
                            </div>
                            <div>
                                <div style={{ fontWeight: 600 }}>{info.name}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{exchange.display_name || exchange.exchange_id}</div>
                            </div>
                        </div>

                        {statsLoading && (
                            <div className="loading" style={{ padding: '10px 0' }}>
                                <div className="loading-spinner"></div>
                            </div>
                        )}

                        {statsError && (
                            <div style={{
                                padding: '8px',
                                borderRadius: '6px',
                                background: 'rgba(220, 50, 47, 0.08)',
                                color: 'var(--color-danger)',
                                fontSize: '11px'
                            }}>
                                {statsError}
                            </div>
                        )}

                        {!statsLoading && !statsError && (
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                                <div className="stat-box">
                                    <div className="stat-label">交易对</div>
                                    <div className="stat-num">{data.total_pairs ?? 0}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">启用交易对</div>
                                    <div className="stat-num">{data.enabled_pairs ?? 0}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">策略数</div>
                                    <div className="stat-num">{data.strategy_count ?? 0}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">订单数</div>
                                    <div className="stat-num">{data.total_orders ?? 0}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">纸面订单</div>
                                    <div className="stat-num">{data.paper_orders ?? 0}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">实盘订单</div>
                                    <div className="stat-num">{data.live_orders ?? 0}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">总收益</div>
                                    <div className="stat-num">{Number(data.total_profit ?? 0).toFixed(4)}</div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">实盘收益</div>
                                    <div className="stat-num">{Number(data.live_profit ?? 0).toFixed(4)}</div>
                                </div>
                            </div>
                        )}
                        <div style={{ display: 'flex', gap: '8px', marginTop: '12px', justifyContent: 'flex-end' }}>
                            <button
                                className="btn btn-secondary"
                                onClick={() => {
                                    onClose();
                                    navigate(`/exchange-pairs?exchange_id=${exchange.id}`);
                                }}
                            >
                                🧩 交易对
                            </button>
                            <button
                                className="btn btn-secondary"
                                onClick={() => {
                                    onClose();
                                    navigate(`/live-assets?exchange_id=${exchange.id}`);
                                }}
                            >
                                🏦 资产
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    if (loading) {
        return (
            <div className="loading">
                <div className="loading-spinner"></div>
            </div>
        );
    }

    return (
        <div>
            {/* 页面标题 */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">交易所管理</h1>
                    <p className="page-subtitle">配置和管理已连接的交易所接口</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button onClick={refresh} className="btn btn-secondary">🔄 刷新</button>
                    <button onClick={() => setShowAddModal(true)} className="btn btn-primary">➕ 添加交易所</button>
                </div>
            </div>

            {/* 统计概览 */}
            <div className="stats-row">
                <div className="stat-box">
                    <div className="stat-label">已配置</div>
                    <div className="stat-num">{exchanges.length}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">已启用</div>
                    <div className="stat-num positive">{exchanges.filter(e => e.is_active && !e.deleted_at).length}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">支持交易所</div>
                    <div className="stat-num">{SUPPORTED_EXCHANGES.length}</div>
                </div>
            </div>

            {/* 交易所表格 */}
            {exchanges.length > 0 ? (
                <div className="data-table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>交易所</th>
                                <th>状态</th>
                                <th>创建时间</th>
                                <th style={{ width: '190px' }}>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            {exchanges.map(exchange => {
                                const info = getExchangeInfo(exchange.exchange_id);
                                const isDeleted = !!exchange.deleted_at;
                                const statusLabel = isDeleted ? '● 已删除' : (exchange.is_active ? '● 已启用' : '○ 已停用');
                                const statusClass = isDeleted ? 'neutral' : (exchange.is_active ? 'success' : 'neutral');
                                return (
                                    <tr key={exchange.id}>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                                <div className="table-avatar" style={{
                                                    background: `linear-gradient(135deg, ${info.color}40, ${info.color}80)`,
                                                    fontSize: '18px'
                                                }}>
                                                    {info.icon}
                                                </div>
                                                <div>
                                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{info.name}</div>
                                                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{exchange.display_name || info.fullName}</div>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <span className={`table-badge ${statusClass}`}>
                                                {statusLabel}
                                            </span>
                                        </td>
                                        <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                                            {exchange.created_at ? new Date(exchange.created_at).toLocaleDateString() : '-'}
                                        </td>
                                        <td>
                                            <div style={{ display: 'flex', gap: '6px' }}>
                                                <button
                                                    onClick={() => navigate(`/exchange-pairs?exchange_id=${exchange.id}`)}
                                                    className="btn btn-sm btn-secondary"
                                                >
                                                    🧩
                                                </button>
                                                <button
                                                    onClick={() => handleStats(exchange)}
                                                    className="btn btn-sm btn-secondary"
                                                >
                                                    📊
                                                </button>
                                                <button
                                                    onClick={() => handleDelete(exchange)}
                                                    className="btn btn-sm btn-danger"
                                                >
                                                    🗑
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="empty-state">
                    <div className="empty-state-icon">🔗</div>
                    <div className="empty-state-title">尚未配置任何交易所</div>
                    <div className="empty-state-desc">点击上方“添加交易所”按钮开始配置您的交易所接口</div>
                </div>
            )}

            {/* 支持的交易所 */}
            <h2 className="section-title" style={{ marginTop: '32px' }}>支持的交易所</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {SUPPORTED_EXCHANGES.map(ex => (
                        <span key={ex.id} className={`table-badge ${ex.setupSupported ? 'success' : 'neutral'}`} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {ex.icon} {ex.name} {ex.setupSupported ? '已接入' : '待接入'}
                        </span>
                ))}
            </div>

            {/* 模态框 */}
            {showAddModal && <AddExchangeModal onClose={() => setShowAddModal(false)} />}
                {deleteTarget && <DeleteExchangeModal exchange={deleteTarget} onClose={() => setDeleteTarget(null)} />}
            {statsTarget && <ExchangeStatsModal exchange={statsTarget} onClose={() => setStatsTarget(null)} />}
        </div>
    );
};

export default ExchangeManagement;
