import React from 'react';

const Dashboard = ({ signals, activeStrategiesCount }) => {
    return (
        <>
            <div className="stats-row">
                <div className="stat-box">
                    <div className="stat-label">活跃策略</div>
                    <div className="stat-num">{activeStrategiesCount}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">捕获信号</div>
                    <div className="stat-num">{signals.length}</div>
                </div>
                <div className="stat-box">
                    <div className="stat-label">预估收益（24小时）</div>
                    <div className="stat-num highlight">+0.000%</div>
                </div>
            </div>

            <div className="data-section">
                <h2 className="section-title">实时套利信号（图搜索）</h2>
                <div className="data-table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>交易路径</th>
                                <th>预估利润</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            {signals.map((signal) => (
                                <tr key={signal.id}>
                                    <td>{signal.timestamp?.toDate().toLocaleTimeString('zh-CN')}</td>
                                    <td><span className="tag">{signal.path}</span></td>
                                    <td style={{ color: '#2aa198', fontWeight: '600' }}>
                                        {(signal.expected_profit * 100).toFixed(3)}%
                                    </td>
                                    <td>{signal.status === 'detected' ? '已捕获' : '进行中'}</td>
                                </tr>
                            ))}
                            {signals.length === 0 && (
                                <tr>
                                    <td colSpan="4" style={{ textAlign: 'center', padding: '2rem', color: '#657b83' }}>
                                        等待图搜索引擎数据...
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </>
    );
};

export default Dashboard;
