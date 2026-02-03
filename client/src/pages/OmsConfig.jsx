import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const STORAGE_KEY = 'inarbit_oms_config';

function parseIntOr(value, fallback) {
    const n = parseInt(String(value ?? ''), 10);
    return Number.isFinite(n) ? n : fallback;
}

function parseBool(value) {
    return value === true || value === 'true' || value === '1' || value === 1;
}

function loadConfig() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function defaultConfig() {
    return {
        trading_mode: 'paper',
        confirm_live: false,
        limit: 20,
        max_rounds: 5,
        sleep_ms: 500,
        max_age_seconds: null,
        auto_cancel: false,
    };
}

const OmsConfig = () => {
    const navigate = useNavigate();
    const initial = useMemo(() => {
        return { ...defaultConfig(), ...(loadConfig() || {}) };
    }, []);

    const [config, setConfig] = useState(initial);
    const [savedAt, setSavedAt] = useState(null);

    useEffect(() => {
        // eslint 规则禁止在 effect 内同步触发 setState 链式更新
        const t = setTimeout(() => {
            setConfig((c) => ({ ...defaultConfig(), ...(loadConfig() || c) }));
        }, 0);
        return () => clearTimeout(t);
    }, []);

    const save = () => {
        const normalized = {
            trading_mode: config.trading_mode === 'live' ? 'live' : 'paper',
            confirm_live: parseBool(config.confirm_live),
            limit: Math.max(1, parseIntOr(config.limit, 20)),
            max_rounds: Math.max(1, parseIntOr(config.max_rounds, 5)),
            sleep_ms: Math.max(0, parseIntOr(config.sleep_ms, 500)),
            max_age_seconds: config.max_age_seconds === null || String(config.max_age_seconds).trim() === '' ? null : Math.max(1, parseIntOr(config.max_age_seconds, null)),
            auto_cancel: parseBool(config.auto_cancel),
        };

        localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
        setConfig(normalized);
        setSavedAt(new Date());
        alert('订单管理配置已保存到本地');
    };

    const reset = () => {
        if (!confirm('确定要重置订单管理配置为默认值吗？')) return;
        const d = defaultConfig();
        localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
        setConfig(d);
        setSavedAt(new Date());
    };

    const fillToConsole = () => {
        navigate('/oms', { state: { preset: config } });
    };

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">订单管理参数配置</h1>
                    <p className="page-subtitle">本地保存默认参数（本地存储），用于订单管理控制台一键填充</p>
                </div>
            </div>

            <div className="stat-box" style={{ padding: '12px', marginBottom: '12px' }}>
                <h3 style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                    默认参数
                </h3>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>交易模式</label>
                        <select
                            value={config.trading_mode}
                            onChange={(e) => setConfig({ ...config, trading_mode: e.target.value })}
                            style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                        >
                            <option value="paper">🟢 模拟</option>
                            <option value="live">🔴 实盘</option>
                        </select>
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>实盘确认开关</label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83', marginTop: '6px' }}>
                            <input
                                type="checkbox"
                                checked={!!config.confirm_live}
                                onChange={(e) => setConfig({ ...config, confirm_live: e.target.checked })}
                            />
                            我已确认实盘风险（仅在实盘模式生效）
                        </label>
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>执行条数</label>
                        <input
                            type="number"
                            value={config.limit}
                            onChange={(e) => setConfig({ ...config, limit: e.target.value })}
                            style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>最大轮数</label>
                        <input
                            type="number"
                            value={config.max_rounds}
                            onChange={(e) => setConfig({ ...config, max_rounds: e.target.value })}
                            style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>轮询间隔（毫秒）</label>
                        <input
                            type="number"
                            value={config.sleep_ms}
                            onChange={(e) => setConfig({ ...config, sleep_ms: e.target.value })}
                            style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>最大计划时长（秒，可空）</label>
                        <input
                            type="number"
                            value={config.max_age_seconds ?? ''}
                            onChange={(e) => setConfig({ ...config, max_age_seconds: e.target.value })}
                            placeholder="留空表示不启用"
                            style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>自动撤单（危险）</label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83', marginTop: '6px' }}>
                            <input
                                type="checkbox"
                                checked={!!config.auto_cancel}
                                onChange={(e) => setConfig({ ...config, auto_cancel: e.target.checked })}
                            />
                            对账超时/轮询耗尽后自动撤单
                        </label>
                    </div>
                </div>

                <div style={{ marginTop: '12px', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary btn-sm" onClick={reset}>重置默认</button>
                    <button className="btn btn-primary btn-sm" onClick={save}>保存配置</button>
                    <button className="btn btn-primary btn-sm" onClick={fillToConsole}>一键填充到订单管理控制台</button>
                </div>

                <div style={{ marginTop: '10px', fontSize: '9px', color: 'var(--text-muted)' }}>
                    {savedAt ? `最近保存：${savedAt.toLocaleString()}` : '未保存（当前显示为本地存储或默认值）'}
                </div>
            </div>

            <div style={{ padding: '10px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px', fontSize: '9px', color: 'var(--text-muted)' }}>
                <strong>提示：</strong> 实盘模式需要后端开启环境变量 INARBIT_ENABLE_LIVE_OMS=1 且已确认实盘。
            </div>
        </div>
    );
};

export default OmsConfig;
