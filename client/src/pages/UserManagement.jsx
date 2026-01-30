import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { authAPI, setAuthToken } from '../api/client';

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
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);

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
        loadProfile();
        return () => { mounted = false; };
    }, []);

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
