/**
 * 全局设置页面
 * 重构版 - 添加系统重置功能
 */
import React, { useEffect, useState } from 'react';
import { configAPI, systemAPI } from '../api/client';

const Settings = () => {
    const [config, setConfig] = useState({
        tradingMode: 'paper',
        defaultStrategy: 'triangular',
        riskLevel: 'medium',
        maxDailyLoss: 500,
        maxPositionSize: 10000,
        enableNotifications: true
    });

    const [loading, setLoading] = useState(true);

    const [resetting, setResetting] = useState(false);

    useEffect(() => {
        let mounted = true;
        const loadSettings = async () => {
            try {
                const res = await configAPI.getGlobalSettings();
                if (!mounted) return;
                const data = res?.data || {};
                setConfig(prev => ({
                    ...prev,
                    tradingMode: data.tradingMode || prev.tradingMode,
                    defaultStrategy: data.defaultStrategy || prev.defaultStrategy,
                    riskLevel: data.riskLevel || prev.riskLevel,
                    maxDailyLoss: data.maxDailyLoss ?? prev.maxDailyLoss,
                    maxPositionSize: data.maxPositionSize ?? prev.maxPositionSize,
                    enableNotifications: data.enableNotifications ?? prev.enableNotifications,
                }));
            } catch (e) {
                console.error(e);
            } finally {
                if (mounted) setLoading(false);
            }
        };
        loadSettings();
        return () => { mounted = false; };
    }, []);

    const handleSave = async () => {
        try {
            await configAPI.updateGlobalSettings({
                tradingMode: config.tradingMode,
                defaultStrategy: config.defaultStrategy,
                riskLevel: config.riskLevel,
                maxDailyLoss: config.maxDailyLoss,
                maxPositionSize: config.maxPositionSize,
                enableNotifications: config.enableNotifications,
            });
            alert('配置已保存');
        } catch (e) {
            alert(e.message || '保存失败');
        }
    };

    // 系统重置需要异步调用后端接口
    const handleSystemReset = async () => {
        if (!confirm('⚠️ 警告！\n\n此操作将：\n1. 清空所有交易所配置\n2. 重置所有策略配置\n3. 清空模拟盘数据\n4. 停止机器人\n\n确定要继续吗？')) {
            return;
        }

        if (!confirm('再次确认：这将删除所有配置数据，此操作不可逆！')) {
            return;
        }

        setResetting(true);
        try {
            await systemAPI.reset({
                confirm: true,
                initial_capital: 1000,
                new_admin_password: 'admin123'
            });
            alert('系统已重置，请重新登录');
            localStorage.removeItem('inarbit_token');
            localStorage.removeItem('inarbit_user');
            window.location.href = '/login';
        } catch (e) {
            alert(e.message || '重置失败');
        } finally {
            setResetting(false);
        }
    };

    return (
        <div className="content-body">
            {/* 页面标题 */}
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">全局设置</h1>
                    <p className="page-subtitle">系统参数与风险配置</p>
                </div>
            </div>

            {/* 设置表单 - 双列布局 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px', opacity: loading ? 0.6 : 1 }}>

                {/* 交易配置 */}
                <div className="stat-box" style={{ padding: '12px' }}>
                    <h3 style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px', borderBottom: '1px solid rgba(0,0,0,0.05)', paddingBottom: '6px' }}>
                        交易配置
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>默认交易模式</label>
                            <select
                                value={config.tradingMode}
                                onChange={e => setConfig({ ...config, tradingMode: e.target.value })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            >
                                <option value="paper">📝 模拟盘</option>
                                <option value="live">💰 实盘</option>
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>默认策略</label>
                            <select
                                value={config.defaultStrategy}
                                onChange={e => setConfig({ ...config, defaultStrategy: e.target.value })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            >
                                <option value="triangular">🔺 三角套利</option>
                                <option value="graph">🕸️ 图搜索套利</option>
                                <option value="funding_rate">💹 期现套利</option>
                                <option value="grid">📊 网格交易</option>
                                <option value="pair">🔄 配对交易</option>
                            </select>
                        </div>
                    </div>
                </div>

                {/* 风险控制 */}
                <div className="stat-box" style={{ padding: '12px' }}>
                    <h3 style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px', borderBottom: '1px solid rgba(0,0,0,0.05)', paddingBottom: '6px' }}>
                        风险控制
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>风险等级</label>
                            <select
                                value={config.riskLevel}
                                onChange={e => setConfig({ ...config, riskLevel: e.target.value })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            >
                                <option value="low">🟢 低风险</option>
                                <option value="medium">🟡 中风险</option>
                                <option value="high">🔴 高风险</option>
                            </select>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>日亏损上限 ($)</label>
                                <input
                                    type="number"
                                    value={config.maxDailyLoss}
                                    onChange={e => setConfig({ ...config, maxDailyLoss: parseFloat(e.target.value) })}
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                                />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>最大持仓 ($)</label>
                                <input
                                    type="number"
                                    value={config.maxPositionSize}
                                    onChange={e => setConfig({ ...config, maxPositionSize: parseFloat(e.target.value) })}
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                                />
                            </div>
                        </div>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: 'var(--text-muted)' }}>
                            <input
                                type="checkbox"
                                checked={!!config.enableNotifications}
                                onChange={e => setConfig({ ...config, enableNotifications: e.target.checked })}
                            />
                            启用通知提醒
                        </label>
                    </div>
                </div>
            </div>

            {/* 保存按钮 */}
            <div style={{ textAlign: 'right', marginBottom: '24px' }}>
                <button onClick={handleSave} className="btn btn-primary">
                    保存配置
                </button>
            </div>

            {/* 系统重置 - 红色警告区域 */}
            <div style={{
                padding: '16px',
                background: 'rgba(220, 50, 47, 0.08)',
                borderRadius: '8px',
                border: '1px solid rgba(220, 50, 47, 0.3)',
                borderLeft: '3px solid var(--color-danger)'
            }}>
                <h3 style={{
                    fontSize: '12px',
                    color: 'var(--color-danger)',
                    marginBottom: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                }}>
                    ⚠️ 危险区域
                </h3>
                <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                    系统重置将清空所有配置数据（交易所密钥、策略配置、模拟盘数据等），此操作不可恢复。
                </p>
                <button
                    onClick={handleSystemReset}
                    disabled={resetting}
                    style={{
                        padding: '8px 16px',
                        background: resetting ? '#ccc' : 'var(--color-danger)',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: resetting ? 'wait' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px'
                    }}
                >
                    {resetting ? '重置中...' : '🗑️ 初始化系统'}
                </button>
            </div>
        </div>
    );
};

export default Settings;
