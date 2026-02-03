/**
 * 控制面板页面
 * 重构版 - 运行状态合并入卡片、四卡两两并排、状态中文化
 */
import React, { useEffect, useState } from 'react';
import { useStrategies, useSignals } from '../api/hooks';
import { botAPI, configAPI } from '../api/client';

const ControlPanel = ({ botStatus, setBotStatus, tradingMode, setTradingMode }) => {
    const isRunning = botStatus === 'running';

    const { strategies } = useStrategies();

    // 运行时间（来自后端 start_timestamp）
    const [startTimestamp, setStartTimestamp] = useState(null);
    const [uptime, setUptime] = useState('00:00:00');
    const { signals } = useSignals();

    useEffect(() => {
        const timer = setInterval(() => {
            if (!isRunning || !startTimestamp) {
                setUptime('00:00:00');
                return;
            }
            const now = Date.now();
            const startMs = Number(startTimestamp) * 1000;
            const elapsed = Math.max(0, now - startMs);
            const hours = Math.floor(elapsed / 3600000);
            const minutes = Math.floor((elapsed % 3600000) / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            setUptime(`${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`);
        }, 1000);
        return () => clearInterval(timer);
    }, [isRunning, startTimestamp]);

    const loadBotStatus = async () => {
        try {
            const res = await botAPI.status();
            const data = res?.data || {};
            if (data.status) setBotStatus(data.status);
            if (data.trading_mode) setTradingMode(data.trading_mode);
            setStartTimestamp(data.start_timestamp || null);
        } catch {
            // ignore
        }
    };

    useEffect(() => {
        // eslint 规则禁止在 effect 内同步触发 setState 链式更新
        const t0 = setTimeout(() => loadBotStatus(), 0);
        const t = setInterval(loadBotStatus, 5000);
        return () => {
            clearTimeout(t0);
            clearInterval(t);
        };
    }, []);

    const enabledStrategyIds = (strategies || [])
        .filter((s) => s.is_enabled)
        .map((s) => s.strategy_type);

    const activeStrategies = enabledStrategyIds;

    const toggleBot = async () => {
        const target = isRunning ? 'stopped' : 'running';
        if (target === 'running' && enabledStrategyIds.length === 0) {
            alert('请先至少启用一个策略后再启动机器人');
            return;
        }
        try {
            if (target === 'running') {
                await botAPI.start();
            } else {
                await botAPI.stop();
            }
            await loadBotStatus();
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    const restartBot = async () => {
        if (!confirm('确认重启机器人？')) return;
        try {
            await botAPI.restart();
            await loadBotStatus();
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    const switchMode = async (mode) => {
        if (isRunning) {
            alert('请先停止机器人再切换模式');
            return;
        }
        try {
            const gs = await configAPI.getGlobalSettings();
            const data = gs?.data || {};
            await configAPI.updateGlobalSettings({
                tradingMode: mode,
                defaultStrategy: data.defaultStrategy,
                riskLevel: data.riskLevel,
                maxDailyLoss: data.maxDailyLoss,
                maxPositionSize: data.maxPositionSize,
                enableNotifications: data.enableNotifications,
            });
            setTradingMode(mode);
            await loadBotStatus();
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    // 策略配置
    const strategyOptions = [
        { id: 'triangular', name: '三角套利', icon: '🔺' },
        { id: 'graph', name: '图搜索套利', icon: '🕸️' },
        { id: 'funding_rate', name: '期现套利', icon: '💹' },
        { id: 'grid', name: '网格交易', icon: '📊' },
        { id: 'pair', name: '配对交易', icon: '🔄' },
    ];

    return (
        <div className="content-body">
            {/* 页面标题 */}
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">控制面板</h1>
                    <p className="page-subtitle">系统状态监控与操作控制</p>
                </div>
            </div>

            {/* 四卡两两并排布局 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>

                {/* 卡片1：运行状态（合并原状态栏信息） */}
                <div className="card">
                    <div className="card-header">
                        <span className="card-title">📊 运行状态</span>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
                            {/* 机器人状态 - 中文显示 */}
                            <div style={{ textAlign: 'center', padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>机器人状态</div>
                                <div style={{
                                    fontSize: '14px',
                                    fontWeight: 700,
                                    color: isRunning ? 'var(--color-success)' : 'var(--color-danger)'
                                }}>
                                    {isRunning ? '运行中' : '已停止'}
                                </div>
                            </div>
                            {/* 交易模式 */}
                            <div style={{ textAlign: 'center', padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>交易模式</div>
                                <div style={{
                                    fontSize: '14px',
                                    fontWeight: 700,
                                    color: tradingMode === 'live' ? 'var(--color-danger)' : 'var(--cyan)'
                                }}>
                                    {tradingMode === 'live' ? '实盘' : '模拟'}
                                </div>
                            </div>
                            {/* 运行时间 */}
                            <div style={{ textAlign: 'center', padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>运行时间</div>
                                <div style={{ fontSize: '14px', fontWeight: 700, fontFamily: 'monospace' }}>{uptime}</div>
                            </div>
                            {/* 实时信号 */}
                            <div style={{ textAlign: 'center', padding: '8px', background: 'rgba(0,0,0,0.02)', borderRadius: '6px' }}>
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>实时信号</div>
                                <div style={{ fontSize: '14px', fontWeight: 700 }}>{(signals || []).length}</div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 卡片2：启停控制 */}
                <div className="card">
                    <div className="card-header">
                        <span className="card-title">🎮 启停控制</span>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <p style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                            控制机器人核心运行循环
                        </p>
                        <button
                            onClick={toggleBot}
                            className={`btn ${isRunning ? 'btn-danger' : 'btn-primary'}`}
                            style={{ width: '100%', fontSize: '12px', padding: '10px' }}
                            disabled={!isRunning && enabledStrategyIds.length === 0}
                        >
                            {isRunning ? '🛑 停止机器人' : '▶️ 启动机器人'}
                        </button>
                        {!isRunning && enabledStrategyIds.length === 0 && (
                            <div style={{
                                marginTop: '8px',
                                fontSize: '9px',
                                color: 'var(--color-warning)',
                                padding: '6px',
                                backgroundColor: 'rgba(253, 203, 110, 0.1)',
                                borderRadius: '4px',
                                textAlign: 'center'
                            }}>
                                ⚠️ 请先在策略管理中启用至少一个策略
                            </div>
                        )}
                    </div>
                </div>

                {/* 卡片3：交易模式切换 */}
                <div className="card">
                    <div className="card-header">
                        <span className="card-title">🔄 交易模式</span>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                            <button
                                onClick={() => switchMode('paper')}
                                disabled={isRunning}
                                className={`btn ${tradingMode === 'paper' ? 'btn-primary' : 'btn-secondary'}`}
                                style={{ flex: 1, fontSize: '11px', padding: '8px' }}
                            >
                                📝 模拟盘
                            </button>
                            <button
                                onClick={() => switchMode('live')}
                                disabled={isRunning}
                                className={`btn ${tradingMode === 'live' ? 'btn-danger' : 'btn-secondary'}`}
                                style={{ flex: 1, fontSize: '11px', padding: '8px' }}
                            >
                                💰 实盘
                            </button>
                        </div>
                        <button
                            onClick={restartBot}
                            className="btn btn-secondary"
                            style={{ width: '100%', fontSize: '11px', padding: '8px' }}
                            disabled={!isRunning}
                        >
                            🔄 重启机器人
                        </button>
                        {isRunning && (
                            <div style={{
                                fontSize: '9px',
                                color: 'var(--color-warning)',
                                padding: '6px',
                                backgroundColor: 'rgba(253, 203, 110, 0.1)',
                                borderRadius: '4px',
                                textAlign: 'center'
                            }}>
                                ⚠️ 停止机器人后可切换模式
                            </div>
                        )}
                    </div>
                </div>

                {/* 卡片4：当前运行策略 */}
                <div className="card">
                    <div className="card-header">
                        <span className="card-title">🎯 当前运行策略</span>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        {activeStrategies.length > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                {activeStrategies.map(strategyId => {
                                    const strategy = strategyOptions.find(s => s.id === strategyId);
                                    return strategy ? (
                                        <div key={strategyId} style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px',
                                            fontSize: '11px',
                                            padding: '8px 10px',
                                            background: 'rgba(133, 153, 0, 0.1)',
                                            borderRadius: '6px',
                                            color: '#859900'
                                        }}>
                                            <span style={{ fontSize: '14px' }}>{strategy.icon}</span>
                                            <span style={{ fontWeight: 600 }}>{strategy.name}</span>
                                        </div>
                                    ) : null;
                                })}
                            </div>
                        ) : (
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)', textAlign: 'center', padding: '16px' }}>
                                未选择策略
                            </div>
                        )}
                    </div>
                </div>

            </div>
        </div>
    );
};

export default ControlPanel;
