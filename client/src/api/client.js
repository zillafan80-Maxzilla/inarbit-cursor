/**
 * API 客户端
 * 连接本地 FastAPI 后端
 */

// 使用相对路径，让 Vite 代理转发请求到后端
const API_BASE_URL = '/api/v1';
// WebSocket 需要使用绝对路径，但使用后端端口
const WS_BASE_URL = import.meta.env.VITE_WS_URL
    || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.hostname}:8000/ws`;


/**
 * 通用 fetch 封装
 */
async function fetchAPI(endpoint, options = {}) {
    const baseUrl = options.baseUrl || API_BASE_URL;
    const url = `${baseUrl}${endpoint}`;

    const token = localStorage.getItem('inarbit_token');
    const timeoutMs = Number(options.timeoutMs || 15000);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
    };

    const { baseUrl: _ignored, timeoutMs: _timeoutIgnored, ...fetchOptions } = options;
    const response = await fetch(url, { ...defaultOptions, ...fetchOptions, signal: controller.signal })
        .finally(() => clearTimeout(timeoutId));

    if (!response.ok) {
        if (response.status === 401) {
            localStorage.removeItem('inarbit_token');
            localStorage.removeItem('inarbit_user');
            if (window.location.pathname !== '/login') {
                window.location.href = '/login';
            }
        }

        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `API Error: ${response.status}`);
    }
    return response.json();
}

export function setAuthToken(token) {
    if (!token) {
        localStorage.removeItem('inarbit_token');
        return;
    }
    localStorage.setItem('inarbit_token', token);
}

export function getAuthToken() {
    return localStorage.getItem('inarbit_token');
}

export const authAPI = {
    login: (payload) => fetchAPI('/auth/login', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),
    logout: () => fetchAPI('/auth/logout', {
        method: 'POST',
    }),
    me: () => fetchAPI('/auth/me'),
    updateProfile: (payload) => fetchAPI('/auth/profile', {
        method: 'PATCH',
        body: JSON.stringify(payload),
    }),
    changePassword: (payload) => fetchAPI('/auth/password', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),
};

// ============================================
// 交易所 API
// ============================================

export const exchangeAPI = {
    list: () => fetchAPI('/exchanges'),

    create: (config) => fetchAPI('/exchanges', {
        method: 'POST',
        body: JSON.stringify(config),
    }),

    delete: (id) => fetchAPI(`/exchanges/${id}`, {
        method: 'DELETE',
    }),
};

export const exchangeV2API = {
    list: () => fetchAPI('/exchanges', { baseUrl: '/api/v2' }),
    setup: (payload) => fetchAPI('/exchanges/setup', {
        method: 'POST',
        body: JSON.stringify(payload),
        baseUrl: '/api/v2',
        timeoutMs: 60000,
    }),
    deleteExchange: (exchangeId, payload) => fetchAPI(`/exchanges/${exchangeId}`, {
        method: 'DELETE',
        body: JSON.stringify(payload),
        baseUrl: '/api/v2',
    }),
    getPairs: (exchangeId, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/exchanges/${exchangeId}/pairs${query ? '?' + query : ''}`, { baseUrl: '/api/v2' });
    },
    togglePair: (exchangeId, pairId, payload) => fetchAPI(`/exchanges/${exchangeId}/pairs/${pairId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
        baseUrl: '/api/v2',
    }),
    stats: (exchangeId) => fetchAPI(`/exchanges/${exchangeId}/stats`, { baseUrl: '/api/v2' }),
    assets: (exchangeId) => fetchAPI(`/exchanges/${exchangeId}/assets`, { baseUrl: '/api/v2' }),
};

// ============================================
// 策略 API
// ============================================

export const strategyAPI = {
    list: () => fetchAPI('/strategies'),

    get: (id) => fetchAPI(`/strategies/${id}`),

    create: (config) => fetchAPI('/strategies', {
        method: 'POST',
        body: JSON.stringify(config),
    }),

    update: (id, updates) => fetchAPI(`/strategies/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(updates),
    }),

    toggle: (id) => fetchAPI(`/strategies/${id}/toggle`, {
        method: 'POST',
    }),
};

// ============================================
// 订单 API
// ============================================

export const orderAPI = {
    list: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/orders${query ? '?' + query : ''}`);
    },
};

// ============================================
// 盈亏 API
// ============================================

export const pnlAPI = {
    summary: () => fetchAPI('/pnl/summary'),

    history: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/pnl/history${query ? '?' + query : ''}`);
    },
};

// ============================================
// 日志 API
// ============================================

export const logAPI = {
    list: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/logs${query ? '?' + query : ''}`);
    },
};

// ============================================
// 行情数据 API
// ============================================

export const marketAPI = {
    getOHLCV: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/market/ohlcv${query ? '?' + query : ''}`);
    },
};

// ============================================
// 统一配置 API（确保各模块数据一致）
// ============================================

export const configAPI = {
    // 获取所有交易所配置
    getExchanges: () => fetchAPI('/config/exchanges'),

    // 获取已连接的交易所
    getConnectedExchanges: () => fetchAPI('/config/exchanges/connected'),

    // 获取指定交易所配置
    getExchange: (exchangeId) => fetchAPI(`/config/exchanges/${exchangeId}`),

    // 获取所有交易对
    getPairs: (exchangeId = null) => {
        const query = exchangeId ? `?exchange_id=${exchangeId}` : '';
        return fetchAPI(`/config/pairs${query}`);
    },

    // 获取指定交易对
    getPair: (symbol) => fetchAPI(`/config/pairs/${symbol.replace('/', '-')}`),

    // 获取所有基础货币
    getCurrencies: () => fetchAPI('/config/currencies'),

    // 机会配置（Graph/Grid/Pair）
    getOpportunityConfigs: () => fetchAPI('/config/opportunity'),
    getOpportunityConfig: (strategyType) => fetchAPI(`/config/opportunity/${strategyType}`),
    updateOpportunityConfig: (strategyType, payload) => fetchAPI(`/config/opportunity/${strategyType}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    }),

    // 获取全局设置
    getGlobalSettings: () => fetchAPI('/config/global'),

    // 获取模拟盘配置
    getSimulationConfig: () => fetchAPI('/config/simulation'),

    // 更新模拟盘配置
    updateSimulationConfig: (payload) => fetchAPI('/config/simulation', {
        method: 'PUT',
        body: JSON.stringify(payload),
    }),

    // 获取模拟盘持仓
    getSimulationPortfolio: () => fetchAPI('/config/simulation/portfolio'),

    // 更新全局设置
    updateGlobalSettings: (payload) => fetchAPI('/config/global', {
        method: 'PUT',
        body: JSON.stringify(payload),
    }),

    // 刷新配置缓存
    refreshCache: () => fetchAPI('/config/cache/refresh', { method: 'POST' }),
};

// ============================================
// 系统管理 API
// ============================================

export const systemAPI = {
    reset: (payload) => fetchAPI('/system/reset', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),
    status: () => fetchAPI('/system/status', { timeoutMs: 60000 }),
    metrics: () => fetchAPI('/system/metrics', { timeoutMs: 60000 }),
};

// ============================================
// 风险监控 API
// ============================================

export const riskAPI = {
    status: () => fetchAPI('/risk/status'),
    panic: () => fetchAPI('/risk/panic', { method: 'POST' }),
    resetPanic: () => fetchAPI('/risk/reset_panic', { method: 'POST' }),
    reloadKeys: () => fetchAPI('/risk/reload_keys', { method: 'POST' }),
};

// ============================================
// 决策与机会 API
// ============================================

export const decisionAPI = {
    getConstraints: () => fetchAPI('/decision/constraints'),
    getAutoConstraints: () => fetchAPI('/decision/constraints/auto'),
    getEffectiveConstraints: () => fetchAPI('/decision/constraints/effective'),
    updateConstraints: (payload) => fetchAPI('/decision/constraints', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),
    listDecisions: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/decision/decisions${query ? '?' + query : ''}`);
    },
    clearDecisions: () => fetchAPI('/decision/decisions/clear', { method: 'POST' }),
};

export const arbitrageAPI = {
    listOpportunities: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/arbitrage/opportunities${query ? '?' + query : ''}`);
    },
    clearOpportunities: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/arbitrage/opportunities/clear${query ? '?' + query : ''}`, { method: 'POST' });
    },
};

// ============================================
// OMS API
// ============================================

export const omsAPI = {
    executeLatest: (payload) => fetchAPI('/oms/execute_latest', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    getPlansLatest: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/plans/latest${query ? '?' + query : ''}`);
    },

    getPlan: (planId, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/plans/${planId}${query ? '?' + query : ''}`);
    },

    getOpportunities: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/opportunities${query ? '?' + query : ''}`);
    },

    getOpportunity: (opportunityId, params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/opportunities/${opportunityId}${query ? '?' + query : ''}`);
    },

    getAlerts: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/alerts${query ? '?' + query : ''}`);
    },

    getOpportunityStats: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/opportunities/stats${query ? '?' + query : ''}`);
    },

    reconcilePlan: (planId, payload) => fetchAPI(`/oms/plans/${planId}/reconcile`, {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    refreshPlan: (planId, payload) => fetchAPI(`/oms/plans/${planId}/refresh`, {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    cancelPlan: (planId, payload) => fetchAPI(`/oms/plans/${planId}/cancel`, {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    getOrders: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/orders${query ? '?' + query : ''}`);
    },

    getFills: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/fills${query ? '?' + query : ''}`);
    },

    refreshOrder: (orderId, payload) => fetchAPI(`/oms/orders/${orderId}/refresh`, {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    cancelOrder: (orderId, payload) => fetchAPI(`/oms/orders/${orderId}/cancel`, {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    preview: (payload) => fetchAPI('/oms/reconcile/preview', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    previewBatch: (payload) => fetchAPI('/oms/reconcile/preview/batch', {
        method: 'POST',
        body: JSON.stringify(payload),
    }),

    getPnLSummary: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/pnl/summary${query ? '?' + query : ''}`);
    },

    getPnLHistory: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchAPI(`/oms/pnl/history${query ? '?' + query : ''}`);
    },
};

// ============================================
// WebSocket 连接
// ============================================

export function createWebSocket(channel) {
    const token = localStorage.getItem('inarbit_token');
    const url = `${WS_BASE_URL}/${channel}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
        console.log(`WebSocket 已连接: ${channel}`);
    };

    ws.onclose = (event) => {
        console.log(`WebSocket 已断开: ${channel} code=${event?.code} reason=${event?.reason || ''}`);
        if (event?.code === 4403) {
            console.warn(`WebSocket 被拒绝(未连接交易所或无权限): ${channel}`);
        }
    };

    ws.onerror = (error) => {
        console.error(`WebSocket 错误: ${channel}`, error);
    };

    return ws;
}

/**
 * 创建带自动重连的 WebSocket
 */
export function createReconnectingWebSocket(channel, onMessage, reconnectInterval = 3000) {
    let ws = null;
    let reconnectTimer = null;
    let isManualClose = false;

    function connect() {
        ws = createWebSocket(channel);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (e) {
                console.warn('无法解析 WebSocket 消息:', event.data);
            }
        };

        ws.onclose = (event) => {
            if (!isManualClose) {
                if (event?.code === 4403) {
                    console.warn(`WebSocket ${channel} 被拒绝(4403)，停止重连`);
                    return;
                }
                console.log(`WebSocket ${channel} 断开，${reconnectInterval / 1000}秒后重连...`);
                reconnectTimer = setTimeout(connect, reconnectInterval);
            }
        };
    }

    connect();

    return {
        close: () => {
            isManualClose = true;
            if (reconnectTimer) clearTimeout(reconnectTimer);
            if (ws) ws.close();
        },
        send: (data) => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(typeof data === 'string' ? data : JSON.stringify(data));
            }
        },
    };
}

/**
 * 创建带自动重连的 WebSocket（支持自定义查询参数）
 */
export function createReconnectingWebSocketWithParams(channel, params = {}, onMessage, reconnectInterval = 3000) {
    let ws = null;
    let reconnectTimer = null;
    let isManualClose = false;

    function buildUrl() {
        const token = localStorage.getItem('inarbit_token');
        const query = new URLSearchParams({
            ...(params || {}),
            ...(token ? { token } : {}),
        });
        return `${WS_BASE_URL}/${channel}?${query.toString()}`;
    }

    function connect() {
        ws = new WebSocket(buildUrl());

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (e) {
                console.warn('无法解析 WebSocket 消息:', event.data);
            }
        };

        ws.onclose = (event) => {
            if (!isManualClose) {
                if (event?.code === 4403) {
                    console.warn(`WebSocket ${channel} 被拒绝(4403)，停止重连`);
                    return;
                }
                reconnectTimer = setTimeout(connect, reconnectInterval);
            }
        };

        ws.onerror = (error) => {
            console.error(`WebSocket 错误: ${channel}`, error);
        };
    }

    connect();

    return {
        close: () => {
            isManualClose = true;
            if (reconnectTimer) clearTimeout(reconnectTimer);
            if (ws) ws.close();
        },
    };
}
