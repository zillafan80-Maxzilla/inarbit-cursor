/**
 * 系统日志页面
 * 实时显示后端推送的日志信息
 */
import React from 'react';
import { useRealtimeLogs } from '../api/hooks';

const Logs = () => {
    const { logs } = useRealtimeLogs();
    const loading = false; // Realtime logs don't have a loading state initially

    // 根据日志级别返回对应颜色
    const getLevelColor = (level) => {
        switch (level?.toUpperCase()) {
            case 'ERROR':
            case 'ALERT':
                return '#dc322f';
            case 'WARNING':
                return '#cb4b16';
            case 'TRADE':
                return '#859900';
            case 'REBALANCE':
                return '#6c71c4';
            default:
                return '#268bd2';
        }
    };

    const getLevelLabel = (level) => {
        switch (level?.toUpperCase()) {
            case 'ERROR':
                return '错误';
            case 'ALERT':
                return '告警';
            case 'WARNING':
                return '警告';
            case 'TRADE':
                return '交易';
            case 'REBALANCE':
                return '再平衡';
            case 'INFO':
                return '信息';
            case 'DEBUG':
                return '调试';
            default:
                return level || '未知';
        }
    };

    return (
        <div className="content-body">
            <h2 className="section-title">系统运行日志</h2>

            {loading && (
                <div style={{ textAlign: 'center', padding: '2rem', color: '#657b83' }}>
                    正在加载系统日志...
                </div>
            )}

            <div className="data-table-container">
                <table className="data-table">
                    <thead>
                        <tr>
                            <th style={{ width: '160px' }}>时间</th>
                            <th style={{ width: '100px' }}>级别</th>
                            <th>消息内容</th>
                        </tr>
                    </thead>
                    <tbody>
                        {logs.map((log) => (
                            <tr key={log.id}>
                                <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                                    {log.timestamp?.toLocaleString('zh-CN', {
                                        hour: '2-digit',
                                        minute: '2-digit',
                                        second: '2-digit',
                                        month: '2-digit',
                                        day: '2-digit'
                                    })}
                                </td>
                                <td>
                                    <span className="tag" style={{
                                        color: getLevelColor(log.level),
                                        backgroundColor: 'transparent',
                                        border: 'none',
                                        fontWeight: '600'
                                    }}>
                                        {getLevelLabel(log.level)}
                                    </span>
                                </td>
                                <td style={{ color: '#657b83' }}>{log.message}</td>
                            </tr>
                        ))}
                        {!loading && logs.length === 0 && (
                            <tr>
                                <td colSpan="3" style={{ textAlign: 'center', padding: '2rem', color: '#657b83' }}>
                                    暂无日志记录，等待后端推送...
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default Logs;
