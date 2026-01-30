/**
 * React Hooks for API
 */
import { useState, useEffect, useCallback } from 'react';
import {
    strategyAPI,
    exchangeV2API,
    orderAPI,
    pnlAPI,
    omsAPI,
    logAPI,
    configAPI,
    createReconnectingWebSocket,
    createReconnectingWebSocketWithParams
} from './client';

// ============================================
// 策略相关 Hooks
// ============================================

export function useStrategies() {
    const [strategies, setStrategies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const refresh = useCallback(async () => {
        try {
            const data = await strategyAPI.list();
            setStrategies(data);
            setError(null);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { strategies, loading, error, refresh };
}

export function useStrategy(id) {
    const [strategy, setStrategy] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!id) return;

        strategyAPI.get(id)
            .then(data => setStrategy(data))
            .finally(() => setLoading(false));
    }, [id]);

    return { strategy, loading };
}

// ============================================
// 交易所相关 Hooks
// ============================================

export function useExchanges() {
    const [exchanges, setExchanges] = useState([]);
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        try {
            const resp = await exchangeV2API.list();
            const list = Array.isArray(resp) ? resp : (resp?.data || []);
            setExchanges(list);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { exchanges, loading, refresh };
}

export function useConnectedExchanges() {
    const [exchanges, setExchanges] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const styleMap = {
        binance: { name: 'Binance', icon: '🟡', bgColor: 'rgba(181, 137, 0, 0.12)', borderColor: '#b58900' },
        okx: { name: 'OKX', icon: '⚪', bgColor: 'rgba(131, 148, 150, 0.12)', borderColor: '#839496' },
        bybit: { name: 'Bybit', icon: '🟠', bgColor: 'rgba(203, 75, 22, 0.10)', borderColor: '#cb4b16' },
        gate: { name: 'Gate.io', icon: '🔵', bgColor: 'rgba(38, 139, 210, 0.10)', borderColor: '#268bd2' },
        bitget: { name: 'Bitget', icon: '🟢', bgColor: 'rgba(133, 153, 0, 0.10)', borderColor: '#859900' },
        mexc: { name: 'MEXC', icon: '🔷', bgColor: 'rgba(38, 139, 210, 0.08)', borderColor: '#268bd2' },
    };

    const normalizeFallback = (list) => {
        return (list || []).map((item) => {
            const exchangeId = item.exchange_id || item.id || '';
            const style = styleMap[String(exchangeId).toLowerCase()] || {};
            return {
                id: exchangeId,
                exchange_id: exchangeId,
                name: item.display_name || style.name || exchangeId,
                icon: style.icon || '🔵',
                bgColor: style.bgColor || 'rgba(0,0,0,0.06)',
                borderColor: style.borderColor || '#666666',
                isConnected: true,
                isSpotEnabled: true,
                isFuturesEnabled: false,
            };
        });
    };

    const refresh = useCallback(async () => {
        setLoading(true);
        const timeoutId = setTimeout(() => {
            setError('加载交易所配置超时');
            setLoading(false);
        }, 15000);
        try {
            const resp = await configAPI.getConnectedExchanges();
            let list = Array.isArray(resp) ? resp : (resp?.data || []);
            if (!list.length) {
                const v2resp = await exchangeV2API.list();
                const v2list = Array.isArray(v2resp) ? v2resp : (v2resp?.data || []);
                const activeList = v2list.filter((item) => item.is_active && !item.deleted_at);
                if (activeList.length) {
                    list = normalizeFallback(activeList);
                }
            }
            setExchanges(list);
            setError(null);
        } catch (e) {
            setError(e.message);
        } finally {
            clearTimeout(timeoutId);
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { exchanges, loading, error, refresh };
}

// ============================================
// 订单相关 Hooks
// ============================================

export function useOrders(params = {}) {
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        orderAPI.list(params)
            .then(data => setOrders(data))
            .finally(() => setLoading(false));
    }, [JSON.stringify(params)]);

    return { orders, loading };
}

// ============================================
// 盈亏相关 Hooks
// ============================================

export function usePnLSummary() {
    const [summary, setSummary] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        pnlAPI.summary()
            .then(data => setSummary(data))
            .finally(() => setLoading(false));
    }, []);

    return { summary, loading };
}

export function usePnLHistory(params = {}) {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        pnlAPI.history(params)
            .then(data => setHistory(data))
            .finally(() => setLoading(false));
    }, [JSON.stringify(params)]);

    return { history, loading };
}

export function useOmsPnLSummary(params = {}) {
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const paramsKey = JSON.stringify(params);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const data = await omsAPI.getPnLSummary(params);
            setSummary(data?.summary ?? data);
        } finally {
            setLoading(false);
        }
    }, [paramsKey]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { summary, loading, refresh };
}

export function useOmsPnLHistory(params = {}) {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const paramsKey = JSON.stringify(params);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const data = await omsAPI.getPnLHistory(params);
            setHistory(data?.history ?? data);
        } finally {
            setLoading(false);
        }
    }, [paramsKey]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    return { history, loading, refresh };
}

// ============================================
// 日志相关 Hooks
// ============================================

export function useLogs(params = {}) {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        logAPI.list(params)
            .then(data => setLogs(data))
            .finally(() => setLoading(false));
    }, [JSON.stringify(params)]);

    return { logs, loading };
}

// ============================================
// WebSocket 实时数据 Hooks
// ============================================

export function useSignals() {
    const [signals, setSignals] = useState([]);

    useEffect(() => {
        const ws = createReconnectingWebSocket('signals', (data) => {
            if (data.type === 'heartbeat') return;

            setSignals(prev => {
                const newSignals = [data, ...prev].slice(0, 50);
                return newSignals;
            });
        });

        return () => ws.close();
    }, []);

    return { signals };
}

export function useTickers(exchange = 'binance') {
    const [tickers, setTickers] = useState({});

    useEffect(() => {
        const ws = createReconnectingWebSocketWithParams(
            `tickers/${exchange}`,
            { limit: 200, interval: 1 },
            (data) => {
                if (data.type === 'tickers') {
                    setTickers(data.data);
                }
            }
        );
        return () => ws.close();
    }, [exchange]);

    return { tickers };
}

export function useTickersMap(exchanges = []) {
    const [tickersByExchange, setTickersByExchange] = useState({});

    useEffect(() => {
        if (!exchanges || exchanges.length === 0) return;

        const ids = exchanges
            .map((ex) => ex.exchange_id || ex.id)
            .filter(Boolean);
        const key = ids.join('|');
        if (!key) return;

        const sockets = ids.map((exchangeId) => {
            return createReconnectingWebSocketWithParams(
                `tickers/${exchangeId}`,
                { limit: 200, interval: 1 },
                (data) => {
                    if (data.type === 'tickers') {
                        setTickersByExchange((prev) => ({
                            ...prev,
                            [exchangeId]: data.data,
                        }));
                    }
                }
            );
        });

        return () => {
            sockets.forEach((ws) => ws.close());
        };
    }, [exchanges]);

    return { tickersByExchange };
}

export function useRealtimeLogs() {
    const [logs, setLogs] = useState([]);

    useEffect(() => {
        const ws = createReconnectingWebSocket('logs', (data) => {
            setLogs(prev => {
                const newLogs = [{ ...data, id: Date.now() }, ...prev].slice(0, 100);
                return newLogs;
            });
        });

        return () => ws.close();
    }, []);

    return { logs };
}
