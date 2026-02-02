import { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const fetchAPI = async (path, options = {}) => {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('auth_token') || ''}`,
      'Content-Type': 'application/json',
      ...options.headers
    }
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
};

export default function EmailReportSettings() {
  const [config, setConfig] = useState({
    enabled: false,
    email: '',
    report_time: '09:00'
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const data = await fetchAPI('/api/v1/user/email-report/config');
      setConfig(data);
    } catch (error) {
      console.error('加载配置失败:', error);
      setMessage('加载失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    try {
      await fetchAPI('/api/v1/user/email-report/config', {
        method: 'POST',
        body: JSON.stringify(config)
      });
      setMessage('✅ 配置已保存');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('❌ 保存失败: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSendTest = async () => {
    setSending(true);
    setMessage('');
    try {
      const result = await fetchAPI('/api/v1/user/email-report/test', {
        method: 'POST'
      });
      setMessage('✅ ' + result.message);
    } catch (error) {
      setMessage('❌ 发送失败: ' + error.message);
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return <div className="content-body">加载中...</div>;
  }

  return (
    <div className="content-body">
      <div className="page-header" style={{ marginBottom: '16px' }}>
        <div>
          <h1 className="page-title">邮件简报设置</h1>
          <p className="page-subtitle">配置每日自动发送交易简报到邮箱</p>
        </div>
      </div>

      <div className="stat-box" style={{ maxWidth: '600px', padding: '24px' }}>
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
              style={{ width: '18px', height: '18px' }}
            />
            <span style={{ fontWeight: '500' }}>启用每日邮件简报</span>
          </label>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500', color: 'var(--text-primary)' }}>
            接收邮箱
          </label>
          <input
            type="email"
            value={config.email}
            onChange={(e) => setConfig({ ...config, email: e.target.value })}
            placeholder="your@email.com"
            className="input"
            style={{ width: '100%', padding: '10px', fontSize: '14px', borderRadius: '4px', border: '1px solid var(--border-color)' }}
          />
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
            邮件简报将发送到此邮箱
          </div>
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500', color: 'var(--text-primary)' }}>
            发送时间
          </label>
          <input
            type="time"
            value={config.report_time}
            onChange={(e) => setConfig({ ...config, report_time: e.target.value })}
            className="input"
            style={{ padding: '10px', fontSize: '14px', borderRadius: '4px', border: '1px solid var(--border-color)' }}
          />
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
            每天在此时间自动发送简报（服务器时区：UTC）
          </div>
        </div>

        <div style={{ marginBottom: '24px', padding: '16px', background: 'rgba(74, 93, 74, 0.05)', borderRadius: '6px', border: '1px solid rgba(74, 93, 74, 0.2)' }}>
          <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '10px' }}>📧 简报内容包括</h3>
          <ul style={{ fontSize: '13px', lineHeight: '1.8', color: 'var(--text-secondary)', listStyle: 'none', padding: 0 }}>
            <li>• 运行模式（模拟/实盘）</li>
            <li>• 启用的交易策略</li>
            <li>• 连接的交易所</li>
            <li>• 交易币对列表</li>
            <li>• 初始资金 / 当前资金 / 净利润</li>
            <li>• 今日订单数 / 今日收益</li>
            <li>• 市场概况与风险状态</li>
          </ul>
        </div>

        {message && (
          <div style={{ 
            padding: '12px', 
            marginBottom: '16px', 
            borderRadius: '4px',
            background: message.includes('✅') ? 'rgba(0, 184, 148, 0.1)' : 'rgba(214, 48, 49, 0.1)',
            color: message.includes('✅') ? '#00b894' : '#d63031',
            fontSize: '14px'
          }}>
            {message}
          </div>
        )}

        <div style={{ display: 'flex', gap: '12px' }}>
          <button 
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary"
            style={{ flex: 1 }}
          >
            {saving ? '保存中...' : '💾 保存配置'}
          </button>
          <button 
            onClick={handleSendTest}
            disabled={sending || !config.email}
            className="btn btn-secondary"
          >
            {sending ? '发送中...' : '📧 发送测试邮件'}
          </button>
        </div>

        <div style={{ marginTop: '20px', padding: '12px', background: 'rgba(255, 193, 7, 0.1)', borderRadius: '4px', fontSize: '12px', color: 'var(--text-secondary)' }}>
          <strong>⚠️ 注意事项:</strong>
          <ul style={{ marginTop: '8px', paddingLeft: '20px' }}>
            <li>需要管理员在服务器配置SMTP设置（server/.env）</li>
            <li>推荐使用Gmail（smtp.gmail.com:587）或企业邮箱</li>
            <li>邮件发送时间基于服务器时区</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
