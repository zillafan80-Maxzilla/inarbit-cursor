import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { authAPI, setAuthToken } from '../api/client';

const Login = ({ onLogin }) => {
    const navigate = useNavigate();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username || !password) return;

        setLoading(true);
        try {
            const res = await authAPI.login({ username, password });
            if (res?.token) {
                setAuthToken(res.token);
                localStorage.setItem('inarbit_user', JSON.stringify(res.user || {}));
                onLogin?.(res.user);
                navigate('/', { replace: true });
            }
        } catch (err) {
            alert(`登录失败: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="content-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '70vh' }}>
            <div className="stat-box" style={{ width: '380px' }}>
                <h2 className="section-title" style={{ marginBottom: '12px' }}>登录</h2>

                <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '10px' }}>
                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>用户名</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            placeholder="管理员"
                            style={{ width: '100%', fontSize: '11px', padding: '8px' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>密码</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            style={{ width: '100%', fontSize: '11px', padding: '8px' }}
                        />
                    </div>

                    <button
                        type="submit"
                        className="btn btn-primary btn-sm"
                        disabled={loading}
                        style={{ marginTop: '6px' }}
                    >
                        {loading ? '登录中...' : '登录'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Login;
