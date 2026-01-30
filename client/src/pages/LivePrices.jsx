import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

import { useConnectedExchanges, useTickersMap } from '../api/hooks';
import { marketAPI } from '../api/client';

/**
 * 实时价格页面
 * 重构版 - 交互式价格曲线图，浮影按钮切换币种
 */
const LivePrices = () => {
    const { exchanges, loading } = useConnectedExchanges();

    const defaultCoins = ['BTC', 'ETH', 'BNB', 'SOL'];
    const preferredCoins = ['BTC', 'ETH', 'BNB', 'SOL', 'BEAM', 'BSW', 'ANC', 'AGIX', 'BLZ'];
    const stableQuotes = ['USDT', 'USDC', 'BUSD', 'FDUSD', 'TUSD', 'DAI'];

    const normalizeCoin = (coin) => String(coin || '').trim().toUpperCase();
    const getCoinLabel = (coin) => normalizeCoin(coin);
    const formatPairLabel = (coin, quote = 'USDT') => `${normalizeCoin(coin)}/${normalizeCoin(quote)}`;
    const formatCoinLabel = (coin) => normalizeCoin(coin);

    const parseSymbol = (symbol) => {
        const raw = String(symbol || '').trim();
        if (!raw) return null;
        const cleaned = raw.replace(/:USDT$/i, '/USDT').replace(/:USDC$/i, '/USDC');
        const parts = cleaned.split(/[\/-]/g).filter(Boolean);
        if (parts.length < 2) return null;
        const base = normalizeCoin(parts[0]);
        const quote = normalizeCoin(parts[1]);
        return { base, quote, normalized: `${base}/${quote}` };
    };

    const getPreferredQuote = (quotes) => {
        for (const q of stableQuotes) {
            if (quotes.includes(q)) return q;
        }
        return quotes[0] || 'USDT';
    };

    const getTimeframe = (period) => {
        switch (period) {
            case '1H':
                return '1m';
            case '1D':
                return '15m';
            case '1W':
                return '1h';
            case '1M':
                return '4h';
            default:
                return '15m';
        }
    };

    const formatPrice = (value) => {
        if (value === null || value === undefined || Number.isNaN(value)) return '-';
        const abs = Math.abs(value);
        let digits = 2;
        if (abs < 1 && abs >= 0.01) digits = 4;
        if (abs < 0.01 && abs >= 0.0001) digits = 6;
        if (abs < 0.0001) digits = 8;
        return `$${Number(value).toLocaleString(undefined, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        })}`;
    };

    // 当前选中的币种（每个交易所独立）
    const [selectedCoins, setSelectedCoins] = useState({});

    // 调试信息开关（取数与曲线对比）
    const [showDebug, setShowDebug] = useState(false);

    // 时间周期选择
    const [timePeriods, setTimePeriods] = useState({});

    const { tickersByExchange } = useTickersMap(exchanges || []);
    const [priceHistory, setPriceHistory] = useState({});
    const [ohlcvCache, setOhlcvCache] = useState({});

    const toNum = (v) => {
        if (v === undefined || v === null || v === '') return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
    };

    const getPriceFromTicker = (ticker) => {
        const last = toNum(ticker?.last);
        if (last !== null) return last;
        const bid = toNum(ticker?.bid);
        const ask = toNum(ticker?.ask);
        if (bid !== null && ask !== null) return (bid + ask) / 2;
        return bid ?? ask ?? null;
    };

    const getPeriodMs = (period) => {
        switch (period) {
            case '1H':
                return 60 * 60 * 1000;
            case '1D':
                return 24 * 60 * 60 * 1000;
            case '1W':
                return 7 * 24 * 60 * 60 * 1000;
            case '1M':
                return 30 * 24 * 60 * 60 * 1000;
            default:
                return 24 * 60 * 60 * 1000;
        }
    };

    const formatTimeLabel = (ts, period) => {
        const d = new Date(ts);
        if (period === '1H' || period === '1D') {
            return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }
        return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
    };

    const enabledExchanges = useMemo(() => (exchanges || []), [exchanges]);

    const normalizedTickersByExchange = useMemo(() => {
        const map = {};
        for (const ex of enabledExchanges) {
            const exchangeId = ex.exchange_id || ex.id;
            if (!exchangeId) continue;
            const tickers = tickersByExchange?.[exchangeId] || {};
            const normalized = {};
            Object.entries(tickers).forEach(([symbol, ticker]) => {
                const parsed = parseSymbol(symbol);
                if (!parsed) return;
                if (!stableQuotes.includes(parsed.quote)) return;
                normalized[`${parsed.base}/${parsed.quote}`] = ticker;
            });
            map[exchangeId] = normalized;
        }
        return map;
    }, [enabledExchanges, tickersByExchange]);

    const coinsByExchange = useMemo(() => {
        const map = {};
        for (const ex of enabledExchanges) {
            const exchangeId = ex.exchange_id || ex.id;
            if (!exchangeId) continue;
            const tickers = normalizedTickersByExchange?.[exchangeId] || {};
            const available = Object.keys(tickers)
                .map((s) => parseSymbol(s))
                .filter(Boolean)
                .map((p) => p.base);
            const unique = Array.from(new Set(available));
            const prioritized = [
                ...preferredCoins.filter((c) => unique.includes(c)),
                ...preferredCoins.filter((c) => !unique.includes(c)),
                ...unique.filter((c) => !preferredCoins.includes(c)),
            ].slice(0, 20);
            map[exchangeId] = prioritized.length ? prioritized : preferredCoins;
        }
        return map;
    }, [enabledExchanges, normalizedTickersByExchange]);

    useEffect(() => {
        if (!enabledExchanges.length) return;

        setSelectedCoins(prev => {
            const next = { ...prev };
            for (const ex of enabledExchanges) {
                const exchangeId = ex.exchange_id || ex.id;
                if (!exchangeId) continue;
                if (!next[exchangeId]) next[exchangeId] = 'BTC';
            }
            return next;
        });
        setTimePeriods(prev => {
            const next = { ...prev };
            for (const ex of enabledExchanges) {
                const exchangeId = ex.exchange_id || ex.id;
                if (!exchangeId) continue;
                if (!next[exchangeId]) next[exchangeId] = '1D';
            }
            return next;
        });
    }, [enabledExchanges]);

    useEffect(() => {
        if (!enabledExchanges.length) return;
        let cancelled = false;

        const loadOhlcv = async () => {
            for (const ex of enabledExchanges) {
                const exchangeId = ex.exchange_id || ex.id;
                if (!exchangeId) continue;
                const availableCoins = coinsByExchange[exchangeId] || defaultCoins;
                const currentCoin = selectedCoins[exchangeId] || availableCoins[0] || 'BTC';
                const period = timePeriods[exchangeId] || '1D';
                const tickers = normalizedTickersByExchange[exchangeId] || {};
                const availableQuotes = Object.keys(tickers)
                    .map((s) => parseSymbol(s))
                    .filter((p) => p && p.base === currentCoin)
                    .map((p) => p.quote);
                const quote = getPreferredQuote(Array.from(new Set(availableQuotes)));
                const symbol = `${currentCoin}/${quote}`;
                const timeframe = getTimeframe(period);
                const cacheKey = `${exchangeId}|${symbol}|${timeframe}`;
                if (ohlcvCache[cacheKey]) continue;

                try {
                    const resp = await marketAPI.getOHLCV({
                        exchange_id: exchangeId,
                        symbol,
                        timeframe,
                        limit: 200,
                    });
                    if (cancelled) return;
                    const items = resp?.items || [];
                    setOhlcvCache((prev) => ({ ...prev, [cacheKey]: items }));
                } catch {
                    if (cancelled) return;
                }
            }
        };

        loadOhlcv();
        return () => { cancelled = true; };
    }, [enabledExchanges, selectedCoins, timePeriods, coinsByExchange, normalizedTickersByExchange]);

    useEffect(() => {
        if (!enabledExchanges.length) return;

        setPriceHistory((prev) => {
            const next = { ...prev };
            const now = Date.now();

            for (const ex of enabledExchanges) {
                const exchangeId = ex.exchange_id || ex.id;
                if (!exchangeId) continue;
                const tickers = normalizedTickersByExchange[exchangeId] || {};
                if (!next[exchangeId]) next[exchangeId] = {};

                Object.entries(tickers).forEach(([symbol, ticker]) => {
                    const price = getPriceFromTicker(ticker);
                    if (price === null) return;
                    const ts = Number(ticker.timestamp) || now;
                    const history = next[exchangeId][symbol] ? [...next[exchangeId][symbol]] : [];
                    const last = history[history.length - 1];
                    if (!last || last.price !== price) {
                        history.push({ time: ts, price });
                    }
                    if (history.length > 500) {
                        history.splice(0, history.length - 500);
                    }
                    next[exchangeId][symbol] = history;
                });
            }

            return next;
        });
    }, [normalizedTickersByExchange, enabledExchanges, coinsByExchange]);

    if (loading) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>⏳</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载交易所配置...</p>
            </div>
        );
    }

    if (!enabledExchanges.length) {
        return (
            <div className="content-body" style={{ textAlign: 'center', padding: '2rem' }}>
                <div style={{ fontSize: '1.5rem' }}>ℹ️</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无已连接交易所，请先在“交易所管理”中添加并连接。</p>
            </div>
        );
    }

    return (
        <div className="content-body">
            {/* 页面标题 */}
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">实时价格</h1>
                    <p className="page-subtitle">各交易所实时行情（来自交易所实时数据）</p>
                </div>
                <div>
                    <button className="btn btn-secondary" onClick={() => setShowDebug((v) => !v)}>
                        {showDebug ? '隐藏取数详情' : '显示取数详情'}
                    </button>
                </div>
            </div>

            {/* 交易所卡片 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {enabledExchanges.map(exchange => {
                    const exchangeId = exchange.exchange_id || exchange.id;
                    const availableCoins = coinsByExchange[exchangeId] || defaultCoins;
                    const currentCoin = selectedCoins[exchangeId] || availableCoins[0] || 'BTC';
                    const period = timePeriods[exchangeId] || '1D';
                    const tickers = normalizedTickersByExchange[exchangeId] || {};
                    const availableQuotes = Object.keys(tickers)
                        .map((s) => parseSymbol(s))
                        .filter((p) => p && p.base === currentCoin)
                        .map((p) => p.quote);
                    const quote = getPreferredQuote(Array.from(new Set(availableQuotes)));
                    const symbol = `${currentCoin}/${quote}`;
                    const history = priceHistory?.[exchangeId]?.[symbol] || [];
                    const rawTicker = normalizedTickersByExchange?.[exchangeId]?.[symbol] || null;
                    const timeframe = getTimeframe(period);
                    const cacheKey = `${exchangeId}|${symbol}|${timeframe}`;
                    const ohlcv = ohlcvCache[cacheKey] || [];
                    const periodMs = getPeriodMs(period);
                    const now = Date.now();
                    const periodHistory = history.filter((p) => now - p.time <= periodMs);
                    const series = ohlcv.length
                        ? ohlcv.map((c) => ({ time: formatTimeLabel(c.timestamp, period), price: Number(c.close) }))
                        : periodHistory.map((p) => ({ time: formatTimeLabel(p.time, period), price: p.price }));
                    const chartData = series;

                    const prices = series.map((p) => p.price).filter((p) => Number.isFinite(p));
                    const currentPrice = prices.length ? prices[prices.length - 1] : null;
                    const high = prices.length ? Math.max(...prices) : null;
                    const low = prices.length ? Math.min(...prices) : null;
                    const first = prices.length ? prices[0] : null;
                    const change = first && currentPrice ? ((currentPrice - first) / first) * 100 : null;

                    return (
                        <div
                            key={exchange.id}
                            style={{
                                background: exchange.bgColor,
                                borderRadius: '16px',
                                border: `1px solid ${exchange.borderColor}25`,
                                borderLeft: `4px solid ${exchange.borderColor}`,
                                padding: '16px',
                                boxShadow: '4px 4px 10px #d9d9d4, -3px -3px 8px #ffffff'
                            }}
                        >
                            {/* 第一行：交易所名称和状态 */}
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                marginBottom: '12px',
                                paddingBottom: '8px',
                                borderBottom: `1px solid ${exchange.borderColor}20`
                            }}>
                                <span style={{ fontSize: '16px' }}>{exchange.icon}</span>
                                <span style={{ fontSize: '14px', fontWeight: 600, color: exchange.borderColor }}>
                                    {exchange.name}
                                </span>
                                <span style={{
                                    marginLeft: 'auto',
                                    fontSize: '10px',
                                    color: 'var(--color-success)',
                                    padding: '3px 8px',
                                    background: 'rgba(133, 153, 0, 0.1)',
                                    borderRadius: '10px'
                                }}>
                                    ● 已连接
                                </span>
                            </div>

                            {/* 第二行：虚拟币对浮影按钮 */}
                            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
                                {availableCoins.map(coin => (
                                    <button
                                        key={coin}
                                        onClick={() => setSelectedCoins(prev => ({ ...prev, [exchangeId]: coin }))}
                                        style={{
                                            flex: '1 0 80px',
                                            padding: '10px 16px',
                                            borderRadius: '12px',
                                            border: 'none',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                            transition: 'all 0.2s ease',
                                            background: currentCoin === coin
                                                ? `linear-gradient(145deg, ${exchange.borderColor}, ${exchange.borderColor}cc)`
                                                : 'linear-gradient(145deg, #f0f0eb, #e0e0db)',
                                            color: currentCoin === coin ? '#fff' : 'var(--primary-green)',
                                            boxShadow: currentCoin === coin
                                                ? `3px 3px 8px ${exchange.borderColor}40`
                                                : '3px 3px 6px #d0d0cb, -2px -2px 5px #ffffff'
                                        }}
                                    >
                                        {formatCoinLabel(coin)}
                                    </button>
                                ))}
                            </div>

                            {/* 当前选中币种的价格信息 */}
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '16px',
                                marginBottom: '12px',
                                padding: '12px',
                                background: 'rgba(255,255,255,0.5)',
                                borderRadius: '10px'
                            }}>
                                <div>
                                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{formatPairLabel(currentCoin, quote)}</div>
                                    <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>
                                        {formatPrice(currentPrice)}
                                    </div>
                                </div>
                                <div style={{
                                    padding: '4px 10px',
                                    borderRadius: '8px',
                                    background: (change ?? 0) >= 0 ? 'rgba(133, 153, 0, 0.1)' : 'rgba(220, 50, 47, 0.1)',
                                    color: (change ?? 0) >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                                    fontSize: '12px',
                                    fontWeight: 600
                                }}>
                                    {change !== null ? `${change >= 0 ? '+' : ''}${change.toFixed(3)}%` : '-'}
                                </div>
                                <div style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>
                                    <span>最高: {formatPrice(high)}</span>
                                    <span style={{ marginLeft: '12px' }}>最低: {formatPrice(low)}</span>
                                </div>
                            </div>

                            {/* 时间周期切换按钮 */}
                            <div style={{ display: 'flex', gap: '6px', marginBottom: '12px' }}>
                                {['1H', '1D', '1W', '1M'].map(period => (
                                    <button
                                        key={period}
                                        onClick={() => setTimePeriods(prev => ({ ...prev, [exchangeId]: period }))}
                                        style={{
                                            padding: '6px 12px',
                                            borderRadius: '8px',
                                            border: 'none',
                                            fontSize: '10px',
                                            fontWeight: 500,
                                            cursor: 'pointer',
                                            background: timePeriods[exchangeId] === period
                                                ? 'var(--primary-green)'
                                                : 'rgba(0,0,0,0.03)',
                                            color: timePeriods[exchangeId] === period
                                                ? '#fff'
                                                : 'var(--text-secondary)',
                                            boxShadow: timePeriods[exchangeId] === period
                                                ? '2px 2px 4px rgba(74, 93, 74, 0.3)'
                                                : 'none'
                                        }}
                                    >
                                        {period === '1H' ? '1小时' : period === '1D' ? '1天' : period === '1W' ? '1周' : '1月'}
                                    </button>
                                ))}
                            </div>

                            {/* 价格曲线图 */}
                            <div style={{ height: '200px', background: 'rgba(255,255,255,0.3)', borderRadius: '10px', padding: '10px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                        <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                        <YAxis
                                            domain={['dataMin - 10', 'dataMax + 10']}
                                            tick={{ fontSize: 9 }}
                                            stroke="var(--text-muted)"
                                            tickFormatter={(v) => `${Number(v).toFixed(4)}`}
                                        />
                                        <Tooltip
                                            contentStyle={{
                                                backgroundColor: 'var(--base3)',
                                                border: '1px solid var(--border-subtle)',
                                                fontSize: '11px',
                                                borderRadius: '8px'
                                            }}
                                            formatter={(value) => [formatPrice(Number(value)), getCoinLabel(currentCoin)]}
                                        />
                                        <Line
                                            type="monotone"
                                            dataKey="price"
                                            stroke={exchange.borderColor}
                                            strokeWidth={2}
                                            dot={false}
                                            activeDot={{ r: 4, fill: exchange.borderColor }}
                                        />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>

                            {/* 取数与曲线对比信息 */}
                            {showDebug && (
                                <div style={{
                                    marginTop: '12px',
                                    padding: '10px',
                                    background: 'rgba(0,0,0,0.02)',
                                    borderRadius: '8px',
                                    fontSize: '10px',
                                    color: 'var(--text-secondary)'
                                }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '8px' }}>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>当前交易对</div>
                                            <div>{symbol}</div>
                                        </div>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>原始行情时间</div>
                                            <div>{rawTicker?.timestamp ? new Date(Number(rawTicker.timestamp)).toLocaleString('zh-CN') : '—'}</div>
                                        </div>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>历史点数</div>
                                            <div>{history.length}（周期内 {periodHistory.length}）</div>
                                        </div>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>K线点数</div>
                                            <div>{ohlcv.length}（周期 {timeframe}）</div>
                                        </div>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>最新价格</div>
                                            <div>{formatPrice(currentPrice)}</div>
                                        </div>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>最新高/低</div>
                                            <div>{formatPrice(high)} / {formatPrice(low)}</div>
                                        </div>
                                        <div>
                                            <div style={{ color: 'var(--text-muted)' }}>最新变动</div>
                                            <div>{change !== null ? `${change >= 0 ? '+' : ''}${change.toFixed(4)}%` : '—'}</div>
                                        </div>
                                    </div>
                                    <div style={{ marginTop: '8px' }}>
                                        <div style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>原始行情字段（last/bid/ask）</div>
                                        <div>
                                            last: {rawTicker?.last ?? '—'} | bid: {rawTicker?.bid ?? '—'} | ask: {rawTicker?.ask ?? '—'}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default LivePrices;
