import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { authAPI, setAuthToken } from '../api/client';

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

/**
 * 用户管理页面
 * 重构版 - 仅保留账户相关功能，交易所密钥统一到ExchangeManagement
 */
const UserManagement = () => {
    const navigate = useNavigate();
    const [profile, setProfile] = useState({
        username: '',
        email: ''
    });
    const [passwordData, setPasswordData] = useState({
        oldPassword: '',
        newPassword: '',
        confirmPassword: ''
    });
    const [emailConfig, setEmailConfig] = useState({
        enabled: false,
        email: '',
        report_time: '09:00'
    });
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [emailSaving, setEmailSaving] = useState(false);
    const [sendingTest, setSendingTest] = useState(false);
    const [emailMessage, setEmailMessage] = useState('');

    useEffect(() => {
        let mounted = true;
        const loadProfile = async () => {
            try {
                const res = await authAPI.me();
                if (!mounted) return;
                const user = res?.user || {};
                setProfile({
                    username: user.username || '',
                    email: user.email || ''
                });
            } catch (e) {
                console.error(e);
            } finally {
                if (mounted) setLoading(false);
            }
        };
        
        const loadEmailConfig = async () => {
            try {
                const data = await fetchAPI('/api/v1/user/email-report/config');
                if (!mounted) return;
                setEmailConfig(data);
            } catch (e) {
                console.error('加载邮件配置失败:', e);
            }
        };
        
        loadProfile();
        loadEmailConfig();
        return () => { mounted = false; };
    }, []);
    
    const handleSaveEmailConfig = async () => {
        setEmailSaving(true);
        setEmailMessage('');
        try {
            await fetchAPI('/api/v1/user/email-report/config', {
                method: 'POST',
                body: JSON.stringify(emailConfig)
            });
            setEmailMessage('✅ 邮件简报配置已保存');
            setTimeout(() => setEmailMessage(''), 3000);
        } catch (error) {
            setEmailMessage('❌ 保存失败: ' + error.message);
        } finally {
            setEmailSaving(false);
        }
    };
    
    const handleSendTestEmail = async () => {
        setSendingTest(true);
        setEmailMessage('');
        try {
            const result = await fetchAPI('/api/v1/user/email-report/test', {
                method: 'POST'
            });
            setEmailMessage('✅ ' + result.message);
        } catch (error) {
            setEmailMessage('❌ 发送失败: ' + error.message);
        } finally {
            setSendingTest(false);
        }
    };

    const handleSaveProfile = async () => {
        setSaving(true);
        try {
            const res = await authAPI.updateProfile({
                username: profile.username,
                email: profile.email
            });
            const user = res?.user || {};
            setProfile({
                username: user.username || profile.username,
                email: user.email || profile.email
            });
            alert('保存成功');
        } catch (e) {
            alert(e.message || '保存失败');
        } finally {
            setSaving(false);
        }
    };

    const handleLogout = async () => {
        try {
            await authAPI.logout();
        } catch {
        }
        setAuthToken(null);
        localStorage.removeItem('inarbit_user');
        navigate('/login', { replace: true });
    };

    const handleChangePassword = async () => {
        if (passwordData.newPassword !== passwordData.confirmPassword) {
            alert('两次输入的密码不一致');
            return;
        }
        try {
            await authAPI.changePassword({
                oldPassword: passwordData.oldPassword,
                newPassword: passwordData.newPassword,
            });
            alert('密码修改成功，请重新登录');
            setPasswordData({ oldPassword: '', newPassword: '', confirmPassword: '' });
            await authAPI.logout();
        } catch (e) {
            alert(e.message || '密码修改失败');
            return;
        }
        setAuthToken(null);
        localStorage.removeItem('inarbit_user');
        navigate('/login', { replace: true });
    };

    return (
        <div className="content-body">
            <h2 className="section-title">账户与密钥</h2>

            <button
                onClick={handleLogout}
                className="btn btn-secondary btn-sm"
                style={{ marginBottom: '12px' }}
            >
                退出登录
            </button>

            {/* 账户信息 */}
            <div className="stat-box" style={{ marginBottom: '1rem', opacity: loading ? 0.6 : 1 }}>
                <h3 style={{ fontSize: '12px', marginBottom: '12px', fontWeight: 500 }}>账户信息</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '10px', alignItems: 'center', maxWidth: '350px' }}>
                    <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>用户名</label>
                    <input
                        type="text"
                        value={profile.username}
                        onChange={(e) => setProfile({ ...profile, username: e.target.value })}
                        style={{ fontSize: '11px', padding: '6px' }}
                    />
                    <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>邮箱</label>
                    <input
                        type="email"
                        value={profile.email}
                        onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                        style={{ fontSize: '11px', padding: '6px' }}
                    />
                </div>
                <button
                    onClick={handleSaveProfile}
                    disabled={saving}
                    className="btn btn-primary btn-sm"
                    style={{ marginTop: '12px' }}
                >
                    {saving ? '保存中...' : '保存'}
                </button>
            </div>

            {/* 密码修改 */}
            <div className="stat-box" style={{ marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '12px', marginBottom: '12px', fontWeight: 500 }}>密码修改</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', maxWidth: '450px' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>旧密码</label>
                        <input
                            type="password"
                            placeholder="••••••"
                            value={passwordData.oldPassword}
                            onChange={(e) => setPasswordData({ ...passwordData, oldPassword: e.target.value })}
                            style={{ width: '100%', fontSize: '11px', padding: '6px' }}
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>新密码</label>
                        <input
                            type="password"
                            placeholder="••••••"
                            value={passwordData.newPassword}
                            onChange={(e) => setPasswordData({ ...passwordData, newPassword: e.target.value })}
                            style={{ width: '100%', fontSize: '11px', padding: '6px' }}
                        />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>确认密码</label>
                        <input
                            type="password"
                            placeholder="••••••"
                            value={passwordData.confirmPassword}
                            onChange={(e) => setPasswordData({ ...passwordData, confirmPassword: e.target.value })}
                            style={{ width: '100%', fontSize: '11px', padding: '6px' }}
                        />
                    </div>
                </div>
                <button onClick={handleChangePassword} className="btn btn-primary btn-sm" style={{ marginTop: '12px' }}>
                    更新密码
                </button>
            </div>

            {/* 邮件简报配置 */}
            <div className="stat-box" style={{ marginBottom: '1rem' }}>
                <h3 style={{ fontSize: '12px', marginBottom: '12px', fontWeight: 500 }}>📧 每日邮件简报</h3>
                
                <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', marginBottom: '12px' }}>
                        <input
                            type="checkbox"
                            checked={emailConfig.enabled}
                            onChange={(e) => setEmailConfig({ ...emailConfig, enabled: e.target.checked })}
                            style={{ width: '16px', height: '16px' }}
                        />
                        <span style={{ fontSize: '11px', fontWeight: '500' }}>启用每日邮件简报</span>
                    </label>
                    
                    <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '10px', alignItems: 'center', maxWidth: '400px' }}>
                        <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>接收邮箱</label>
                        <input
                            type="email"
                            value={emailConfig.email}
                            onChange={(e) => setEmailConfig({ ...emailConfig, email: e.target.value })}
                            placeholder="your@email.com"
                            style={{ fontSize: '11px', padding: '6px' }}
                        />
                        <label style={{ fontSize: '10px', color: 'var(--text-muted)' }}>发送时间</label>
                        <input
                            type="time"
                            value={emailConfig.report_time}
                            onChange={(e) => setEmailConfig({ ...emailConfig, report_time: e.target.value })}
                            style={{ fontSize: '11px', padding: '6px', width: '120px' }}
                        />
                    </div>
                </div>
                
                <div style={{ marginBottom: '16px', padding: '10px', background: 'rgba(74, 93, 74, 0.05)', borderRadius: '4px', fontSize: '10px', color: 'var(--text-secondary)' }}>
                    <strong>简报内容:</strong> 运行模式、启用策略、交易所、币对、资金收益、今日交易、市场概况
                </div>
                
                {emailMessage && (
                    <div style={{ 
                        padding: '10px', 
                        marginBottom: '12px', 
                        borderRadius: '4px',
                        background: emailMessage.includes('✅') ? 'rgba(0, 184, 148, 0.1)' : 'rgba(214, 48, 49, 0.1)',
                        color: emailMessage.includes('✅') ? '#00b894' : '#d63031',
                        fontSize: '11px'
                    }}>
                        {emailMessage}
                    </div>
                )}
                
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button 
                        onClick={handleSaveEmailConfig}
                        disabled={emailSaving}
                        className="btn btn-primary btn-sm"
                    >
                        {emailSaving ? '保存中...' : '💾 保存邮件配置'}
                    </button>
                    <button 
                        onClick={handleSendTestEmail}
                        disabled={sendingTest || !emailConfig.email}
                        className="btn btn-secondary btn-sm"
                    >
                        {sendingTest ? '发送中...' : '📧 发送测试邮件'}
                    </button>
                </div>
            </div>

            {/* 交易所密钥提示 */}
            <div style={{
                padding: '12px',
                background: 'rgba(133, 153, 0, 0.08)',
                borderRadius: '6px',
                fontSize: '10px',
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }}>
                🔗 交易所接口密钥管理已移至
                <Link to="/exchanges" style={{ color: 'var(--primary-green)', fontWeight: 600 }}>
                    系统配置 → 交易所管理
                </Link>
            </div>
        </div>
    );
};

export default UserManagement;
