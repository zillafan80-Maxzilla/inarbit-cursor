import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, ReferenceLine } from 'recharts';
import { useLocation } from 'react-router-dom';
import { createReconnectingWebSocket, omsAPI } from '../api/client';

const STORAGE_KEY = 'inarbit_oms_config';

function parseIntOr(value, fallback) {
    const n = parseInt(String(value ?? ''), 10);
    return Number.isFinite(n) ? n : fallback;
}

function parseBool(value) {
    return value === true || value === 'true' || value === '1' || value === 1;
}

function normalizeConfig(input) {
    const cfg = input && typeof input === 'object' ? input : {};
    const maxAgeRaw = cfg.max_age_seconds;
    const maxAge =
        maxAgeRaw === null || String(maxAgeRaw).trim() === ''
            ? null
            : (() => {
                const n = parseIntOr(maxAgeRaw, NaN);
                return Number.isFinite(n) ? Math.max(1, n) : null;
            })();
    return {
        trading_mode: cfg.trading_mode === 'live' ? 'live' : 'paper',
        confirm_live: parseBool(cfg.confirm_live),
        idempotency_key: String(cfg.idempotency_key ?? ''),
        limit: Math.max(1, parseIntOr(cfg.limit, 20)),
        max_rounds: Math.max(1, parseIntOr(cfg.max_rounds, 5)),
        sleep_ms: Math.max(0, parseIntOr(cfg.sleep_ms, 500)),
        max_age_seconds: maxAge,
        auto_cancel: parseBool(cfg.auto_cancel),
    };
}

function safeJson(v) {
    try {
        const seen = new WeakSet();
        const s = JSON.stringify(
            v,
            (k, val) => {
                if (k === 'metadata') return '[已省略]';
                if (typeof val === 'string' && val.length > 2000) return `${val.slice(0, 2000)}…（已截断）`;
                if (val && typeof val === 'object') {
                    if (seen.has(val)) return '[循环引用]';
                    seen.add(val);
                }
                return val;
            },
            2
        );
        if (typeof s === 'string' && s.length > 20000) return `${s.slice(0, 20000)}\n…（已截断）`;
        return s;
    } catch {
        return String(v);
    }
}

function extractLegInsights(legs) {
    const list = Array.isArray(legs) ? legs : [];
    const executionSummaries = list.filter((x) => x && typeof x === 'object' && x.kind === 'execution_summary');
    const reconcileSuggestions = list.filter((x) => x && typeof x === 'object' && x.kind === 'reconcile_suggested_request');
    const pnlSummaries = list.filter((x) => x && typeof x === 'object' && x.kind === 'pnl_summary');

    const executionSummary = executionSummaries.length ? executionSummaries[executionSummaries.length - 1] : null;
    const reconcileSuggested = reconcileSuggestions.length ? reconcileSuggestions[reconcileSuggestions.length - 1] : null;
    const pnlSummary = pnlSummaries.length ? pnlSummaries[pnlSummaries.length - 1] : null;

    const suggestedRequest =
        (executionSummary && executionSummary.reconcile_suggested_request) ||
        (reconcileSuggested && reconcileSuggested.request) ||
        null;

    return { executionSummary, reconcileSuggested, suggestedRequest, pnlSummary };
}

function loadConfig() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

function defaultConfig() {
    return {
        trading_mode: 'paper',
        confirm_live: false,
        idempotency_key: '',
        limit: 20,
        max_rounds: 5,
        sleep_ms: 500,
        max_age_seconds: null,
        auto_cancel: false,
    };
}

const OmsConsole = () => {
    const location = useLocation();
    const statusLabelMap = {
        pending: '待处理',
        filled: '已成交',
        cancelled: '已取消',
        canceled: '已取消',
        rejected: '已拒绝',
        partial: '部分成交',
        partially_filled: '部分成交',
        partial_filled: '部分成交',
        new: '新建',
        open: '未完成',
        closed: '已完成',
        done: '已完成',
        failed: '失败',
        unknown: '未知',
    };
    const sideLabelMap = {
        buy: '买入',
        sell: '卖出',
    };
    const accountLabelMap = {
        spot: '现货',
        margin: '杠杆',
        futures: '合约',
        delivery: '交割合约',
        cross: '全仓',
        isolated: '逐仓',
    };
    const planKindLabelMap = {
        triangular: '三角套利',
        cashcarry: '期现套利',
        graph: '图搜索套利',
        multi: '多腿套利',
    };
    const planStageLabelMap = {
        execution_summary: '执行摘要',
        reconcile_summary: '对账摘要',
        pnl_summary: '收益摘要',
    };
    const getStatusLabel = (status) => statusLabelMap[String(status || '').toLowerCase()] || '未知';
    const getSideLabel = (side) => sideLabelMap[String(side || '').toLowerCase()] || '未知';
    const getAccountLabel = (acct) => accountLabelMap[String(acct || '').toLowerCase()] || '未知';
    const getPlanKindLabel = (kind) => planKindLabelMap[String(kind || '').toLowerCase()] || '未知';

    const preset = location?.state?.preset;
    const initialCfg = useMemo(() => ({ ...defaultConfig(), ...(loadConfig() || {}), ...(preset || {}) }), [preset]);

    const [cfg, setCfg] = useState(initialCfg);
    const [defaultsSavedAt, setDefaultsSavedAt] = useState(null);
    const [planId, setPlanId] = useState('');

    const [loading, setLoading] = useState(false);
    const [output, setOutput] = useState('');

    const [orderUpdates, setOrderUpdates] = useState([]);
    const [showOrderRaw, setShowOrderRaw] = useState(false);
    const [orderFilter, setOrderFilter] = useState({
        status: 'all',
        orderId: '',
        paused: false,
    });
    const [orderKeep, setOrderKeep] = useState(100);

    const [plans, setPlans] = useState([]);

    const [orderList, setOrderList] = useState([]);
    const [fillList, setFillList] = useState([]);
    const [listLoading, setListLoading] = useState(false);
    const [autoRefresh, setAutoRefresh] = useState(false);
    const [autoRefreshMs, setAutoRefreshMs] = useState(5000);
    const [autoRefreshPlanOnly, setAutoRefreshPlanOnly] = useState(true);
    const [autoRefreshPlanPnL, setAutoRefreshPlanPnL] = useState(true);

    const defaultOrderQuery = {
        status: '',
        symbol: '',
        account_type: '',
        created_after: '',
        created_before: '',
        offset: 0,
    };
    const defaultFillQuery = {
        symbol: '',
        account_type: '',
        created_after: '',
        created_before: '',
        offset: 0,
    };

    const [orderQuery, setOrderQuery] = useState(defaultOrderQuery);
    const [fillQuery, setFillQuery] = useState(defaultFillQuery);

    const [planDetail, setPlanDetail] = useState(null);
    const [planDetailLoading, setPlanDetailLoading] = useState(false);
    const [planDetailError, setPlanDetailError] = useState('');
    const [opportunityDetail, setOpportunityDetail] = useState(null);
    const [opportunityLoading, setOpportunityLoading] = useState(false);
    const [opportunityError, setOpportunityError] = useState('');
    const [planPnL, setPlanPnL] = useState([]);
    const [planPnLLoading, setPlanPnLLoading] = useState(false);
    const [planPnLError, setPlanPnLError] = useState('');
    const [planPnLUpdatedAt, setPlanPnLUpdatedAt] = useState('');
    const [planPnLWindow, setPlanPnLWindow] = useState('15m');
    const [alertList, setAlertList] = useState([]);
    const [alertLoading, setAlertLoading] = useState(false);
    const [alertError, setAlertError] = useState('');
    const [alertLimit, setAlertLimit] = useState(20);
    const [alertOffset, setAlertOffset] = useState(0);
    const [alertStats, setAlertStats] = useState(null);
    const [alertQuery, setAlertQuery] = useState({
        level: '',
        category: '',
        created_after: '',
        created_before: '',
    });
    const [oppList, setOppList] = useState([]);
    const [oppStats, setOppStats] = useState(null);
    const [oppLoading, setOppLoading] = useState(false);
    const [oppError, setOppError] = useState('');
    const [oppQuery, setOppQuery] = useState({ status: '', kind: '', limit: 20 });
    const [planMarkerFilter, setPlanMarkerFilter] = useState({
        execution: true,
        reconcile: true,
        pnl: true,
    });

    const [previewReq, setPreviewReq] = useState({
        terminal: false,
        auto_cancel: false,
        timeout: false,
        max_rounds_exhausted: false,
        last_status_counts: { pending: 1 },
    });

    const appendOrderUpdate = useCallback((payload) => {
        if (orderFilter.paused) return;
        setOrderUpdates((prev) => {
            const next = [
                {
                    received_at: new Date().toISOString(),
                    payload,
                },
                ...prev,
            ];
            const limit = Math.max(10, Number(orderKeep) || 100);
            return next.slice(0, limit);
        });
    }, [orderFilter.paused, orderKeep]);

    useEffect(() => {
        const socket = createReconnectingWebSocket('orders', appendOrderUpdate, 3000);
        return () => socket.close();
    }, [appendOrderUpdate]);

    const filteredOrderUpdates = useMemo(() => {
        let list = orderUpdates;
        if (orderFilter.status !== 'all') {
            list = list.filter((item) => item?.payload?.status === orderFilter.status);
        }
        if (orderFilter.orderId.trim()) {
            const q = orderFilter.orderId.trim().toLowerCase();
            list = list.filter((item) => String(item?.payload?.order_id || '').toLowerCase().includes(q));
        }
        return list;
    }, [orderUpdates, orderFilter.orderId, orderFilter.status]);

    const orderStatusCounts = useMemo(() => {
        const counts = {};
        for (const item of filteredOrderUpdates) {
            const st = item?.payload?.status || 'unknown';
            counts[st] = (counts[st] || 0) + 1;
        }
        return counts;
    }, [filteredOrderUpdates]);

    const orderListSummary = useMemo(() => {
        const counts = {};
        for (const o of orderList || []) {
            const st = o?.status || 'unknown';
            counts[st] = (counts[st] || 0) + 1;
        }
        return {
            total: (orderList || []).length,
            statusCounts: counts,
        };
    }, [orderList]);

    const fillListSummary = useMemo(() => {
        let totalFee = 0;
        const feeCurrencies = new Set();
        const bySymbol = {};
        const byAccount = {};
        const bySide = {
            buy_qty: 0,
            sell_qty: 0,
            buy_notional: 0,
            sell_notional: 0,
        };

        const orderSideMap = {};
        for (const o of orderList || []) {
            if (o?.id) orderSideMap[String(o.id)] = (o.side || '').toLowerCase();
        }
        for (const f of fillList || []) {
            const fee = Number(f?.fee || 0);
            if (!Number.isNaN(fee)) totalFee += fee;
            if (f?.fee_currency) feeCurrencies.add(f.fee_currency);
            const sym = f?.symbol || '未知';
            const qty = Number(f?.quantity || 0);
            bySymbol[sym] = (bySymbol[sym] || 0) + (Number.isNaN(qty) ? 0 : qty);

            const acct = f?.account_type || '未知';
            byAccount[acct] = (byAccount[acct] || 0) + (Number.isNaN(qty) ? 0 : qty);

            const side = orderSideMap[String(f?.order_id)] || '未知';
            const price = Number(f?.price || 0);
            const notional = (!Number.isNaN(qty) && !Number.isNaN(price)) ? qty * price : 0;
            if (side === 'buy') {
                bySide.buy_qty += Number.isNaN(qty) ? 0 : qty;
                bySide.buy_notional += Number.isNaN(notional) ? 0 : notional;
            } else if (side === 'sell') {
                bySide.sell_qty += Number.isNaN(qty) ? 0 : qty;
                bySide.sell_notional += Number.isNaN(notional) ? 0 : notional;
            }
        }
        return {
            total: (fillList || []).length,
            totalFee: totalFee.toFixed(8),
            feeCurrencies: Array.from(feeCurrencies).join(', ') || '-',
            bySymbol,
            byAccount,
            bySide,
            roughPnL: (bySide.sell_notional - bySide.buy_notional - totalFee).toFixed(8),
        };
    }, [fillList, orderList]);

    const planPnLSummary = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        if (!rows.length) {
            return {
                total: 0,
                totalProfit: 0,
                winRate: 0,
                avgProfit: 0,
            };
        }
        const profits = rows.map((r) => Number(r?.profit || 0)).filter((v) => !Number.isNaN(v));
        const totalProfit = profits.reduce((a, b) => a + b, 0);
        const wins = profits.filter((v) => v > 0).length;
        const total = profits.length;
        return {
            total,
            totalProfit,
            winRate: total ? wins / total : 0,
            avgProfit: total ? totalProfit / total : 0,
        };
    }, [planPnL]);

    const planPnLChart = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        if (!rows.length) return [];
        const sorted = [...rows].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
        let acc = 0;
        return sorted.map((row) => {
            const profit = Number(row?.profit || 0);
            acc += Number.isNaN(profit) ? 0 : profit;
            const ts = row?.created_at || row?.exit_time || row?.entry_time || '';
            const label = ts ? String(ts).slice(11, 19) : '--:--:--';
            return { time: label, value: Number(acc.toFixed(6)) };
        });
    }, [planPnL]);

    const planPnLSymbols = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        const map = new Map();
        rows.forEach((row) => {
            const key = row?.symbol || '多币种';
            const profit = Number(row?.profit || 0);
            map.set(key, (map.get(key) || 0) + (Number.isNaN(profit) ? 0 : profit));
        });
        return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
    }, [planPnL]);

    const planPnLWindowBuckets = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        if (!rows.length) return [];

        const windowMs = planPnLWindow === '5m'
            ? 5 * 60 * 1000
            : planPnLWindow === '1h'
                ? 60 * 60 * 1000
                : 15 * 60 * 1000;

        const buckets = new Map();
        rows.forEach((row) => {
            const ts = row?.created_at || row?.exit_time || row?.entry_time;
            const dt = ts ? new Date(ts) : new Date();
            const bucketTime = new Date(Math.floor(dt.getTime() / windowMs) * windowMs);
            const key = bucketTime.toISOString();
            const profit = Number(row?.profit || 0);
            buckets.set(key, (buckets.get(key) || 0) + (Number.isNaN(profit) ? 0 : profit));
        });

        return Array.from(buckets.entries())
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([key, value]) => ({
                time: key.slice(11, 16),
                value: Number(value.toFixed(6)),
            }));
    }, [planPnL, planPnLWindow]);

    const planPnLExchangeBreakdown = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        const map = new Map();
        rows.forEach((row) => {
            const key = row?.exchange_id || '未知';
            const profit = Number(row?.profit || 0);
            map.set(key, (map.get(key) || 0) + (Number.isNaN(profit) ? 0 : profit));
        });
        return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
    }, [planPnL]);

    const planPnLRiskMetrics = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        if (!rows.length) {
            return { range: 0, maxDrawdown: 0 };
        }
        const sorted = [...rows].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
        let equity = 0;
        let peak = 0;
        let maxDrawdown = 0;
        let minProfit = Infinity;
        let maxProfit = -Infinity;
        for (const row of sorted) {
            const profit = Number(row?.profit || 0);
            const val = Number.isNaN(profit) ? 0 : profit;
            minProfit = Math.min(minProfit, val);
            maxProfit = Math.max(maxProfit, val);
            equity += val;
            if (equity > peak) peak = equity;
            const dd = peak - equity;
            if (dd > maxDrawdown) maxDrawdown = dd;
        }
        const range = maxProfit - minProfit;
        return { range, maxDrawdown };
    }, [planPnL]);

    const planPnLDrawdownCurve = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        if (!rows.length) return [];
        const sorted = [...rows].sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
        let equity = 0;
        let peak = 0;
        return sorted.map((row) => {
            const profit = Number(row?.profit || 0);
            const val = Number.isNaN(profit) ? 0 : profit;
            equity += val;
            if (equity > peak) peak = equity;
            const dd = peak - equity;
            const ts = row?.created_at || row?.exit_time || row?.entry_time || '';
            const label = ts ? String(ts).slice(11, 19) : '--:--:--';
            return { time: label, equity: Number(equity.toFixed(6)), drawdown: Number(dd.toFixed(6)) };
        });
    }, [planPnL]);

    const planPnLDistribution = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        const profits = rows.map((r) => Number(r?.profit || 0)).filter((v) => !Number.isNaN(v));
        if (!profits.length) return [];
        const min = Math.min(...profits);
        const max = Math.max(...profits);
        const bins = 8;
        const width = max === min ? 1 : (max - min) / bins;
        const counts = Array.from({ length: bins }, (_, i) => ({
            bucket: `${(min + i * width).toFixed(4)}~${(min + (i + 1) * width).toFixed(4)}`,
            count: 0,
        }));
        profits.forEach((v) => {
            const idx = width === 0 ? 0 : Math.min(bins - 1, Math.floor((v - min) / width));
            counts[idx].count += 1;
        });
        return counts;
    }, [planPnL]);

    const planPnLQuantiles = useMemo(() => {
        const rows = Array.isArray(planPnL) ? planPnL : [];
        const profits = rows.map((r) => Number(r?.profit || 0)).filter((v) => !Number.isNaN(v)).sort((a, b) => a - b);
        if (!profits.length) return { p10: 0, p50: 0, p90: 0 };
        const pick = (p) => {
            const idx = Math.min(profits.length - 1, Math.max(0, Math.floor(p * (profits.length - 1))));
            return profits[idx];
        };
        return { p10: pick(0.1), p50: pick(0.5), p90: pick(0.9) };
    }, [planPnL]);

    const planStageMarkers = useMemo(() => {
        const legs = Array.isArray(planDetail?.legs) ? planDetail.legs : [];
        if (!legs.length) return [];
        const pickTime = (item) => {
            const raw = item?.created_at || item?.timestamp || item?.ts || item?.time;
            if (!raw) return null;
            const dt = new Date(raw);
            if (Number.isNaN(dt.getTime())) return null;
            return dt.toISOString().slice(11, 19);
        };
        const markers = [];
        for (const leg of legs) {
            if (!leg || typeof leg !== 'object') continue;
            const kind = String(leg.kind || '').toLowerCase();
            if (!['execution_summary', 'reconcile_summary', 'pnl_summary'].includes(kind)) continue;
            const time = pickTime(leg) || pickTime(leg.summary) || pickTime(leg.request);
            if (!time) continue;
            markers.push({ time, kind, label: planStageLabelMap[kind] || '阶段标记' });
        }
        return markers;
    }, [planDetail?.legs]);

    const filteredPlanStageMarkers = useMemo(() => {
        return planStageMarkers.filter((m) => {
            const kind = String(m.kind || '').toLowerCase();
            if (kind === 'execution_summary') return planMarkerFilter.execution;
            if (kind === 'reconcile_summary') return planMarkerFilter.reconcile;
            if (kind === 'pnl_summary') return planMarkerFilter.pnl;
            return true;
        });
    }, [planStageMarkers, planMarkerFilter]);

    const lastOrderUpdateAt = filteredOrderUpdates[0]?.received_at || '';

    useEffect(() => {
        if (preset) {
            setCfg((c) => ({ ...c, ...preset }));
        }
    }, [preset]);

    const write = (v) => setOutput(typeof v === 'string' ? v : safeJson(v));

    const downloadText = (filename, content, mime = 'text/plain') => {
        const blob = new Blob([content], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    };

    const buildExportSuffix = (mode, query) => {
        const labelMap = {
            plan: '计划',
            plan_pnl: '计划收益',
            plan_pnl_report: '计划收益报告',
            orders: '订单',
            orders_filtered: '筛选订单',
            fills: '成交',
            fills_filtered: '筛选成交',
        };
        const parts = [labelMap[mode] || '导出'];
        if (planId) parts.push(`计划编号-${String(planId).slice(0, 8)}`);
        if (query?.created_after) parts.push(`开始-${query.created_after}`);
        if (query?.created_before) parts.push(`结束-${query.created_before}`);
        return parts.join('_').replace(/[:]/g, '-');
    };

    const toCsv = (rows, columns) => {
        const header = columns.map((c) => c.label).join(',');
        const lines = rows.map((row) => (
            columns.map((c) => {
                const val = row?.[c.key] ?? '';
                const s = String(val).replace(/"/g, '""');
                return `"${s}"`;
            }).join(',')
        ));
        return [header, ...lines].join('\n');
    };

    const exportCurrentPlan = (format) => {
        if (!planId) {
            alert('请先选择计划');
            return;
        }
        const planOrders = (orderList || []).filter((o) => String(o?.plan_id || '') === String(planId));
        const orderIds = new Set(planOrders.map((o) => String(o?.id || '')).filter(Boolean));
        const planFills = (fillList || []).filter((f) => orderIds.has(String(f?.order_id || '')));
        const suffix = buildExportSuffix('plan', { created_after: orderQuery.created_after || fillQuery.created_after, created_before: orderQuery.created_before || fillQuery.created_before });

        if (format === 'json') {
            downloadText(`${suffix}_订单.json`, JSON.stringify(planOrders, null, 2), 'application/json');
            downloadText(`${suffix}_成交.json`, JSON.stringify(planFills, null, 2), 'application/json');
            return;
        }

        const ordersCsv = toCsv(planOrders, [
            { key: 'created_at', label: '创建时间' },
            { key: 'status', label: '状态' },
            { key: 'id', label: '订单编号' },
            { key: 'symbol', label: '交易对' },
            { key: 'side', label: '方向' },
            { key: 'plan_id', label: '计划编号' },
            { key: 'filled_quantity', label: '成交数量' },
            { key: 'average_price', label: '成交均价' },
        ]);
        const fillsCsv = toCsv(planFills, [
            { key: 'created_at', label: '创建时间' },
            { key: 'id', label: '成交编号' },
            { key: 'order_id', label: '订单编号' },
            { key: 'symbol', label: '交易对' },
            { key: 'quantity', label: '数量' },
            { key: 'price', label: '价格' },
            { key: 'fee', label: '手续费' },
            { key: 'fee_currency', label: '手续费币种' },
        ]);
        downloadText(`${suffix}_订单.csv`, ordersCsv, 'text/csv');
        downloadText(`${suffix}_成交.csv`, fillsCsv, 'text/csv');
    };

    const exportPlanPnL = (format) => {
        if (!planId) {
            alert('请先选择计划');
            return;
        }
        const rows = Array.isArray(planPnL) ? planPnL : [];
        const suffix = buildExportSuffix('plan_pnl', { created_after: orderQuery.created_after || fillQuery.created_after, created_before: orderQuery.created_before || fillQuery.created_before });

        if (format === 'json') {
            downloadText(`${suffix}.json`, JSON.stringify(rows, null, 2), 'application/json');
            return;
        }

        const csv = toCsv(rows, [
            { key: 'created_at', label: '创建时间' },
            { key: 'exchange_id', label: '交易所' },
            { key: 'symbol', label: '交易对' },
            { key: 'profit', label: '收益' },
            { key: 'profit_rate', label: '收益率' },
            { key: 'quantity', label: '数量' },
        ]);
        downloadText(`${suffix}.csv`, csv, 'text/csv');
    };

    const exportPlanPnLReport = () => {
        if (!planId) {
            alert('请先选择计划');
            return;
        }
        const report = {
            plan_id: String(planId),
            trading_mode: cfg.trading_mode,
            updated_at: planPnLUpdatedAt,
            summary: planPnLSummary,
            risk: planPnLRiskMetrics,
            quantiles: planPnLQuantiles,
            window: planPnLWindow,
            window_buckets: planPnLWindowBuckets,
            equity_drawdown: planPnLDrawdownCurve,
            stage_markers: filteredPlanStageMarkers,
            symbol_breakdown: planPnLSymbols,
            exchange_breakdown: planPnLExchangeBreakdown,
            rows: Array.isArray(planPnL) ? planPnL : [],
        };
        const suffix = buildExportSuffix('plan_pnl_report', { created_after: orderQuery.created_after || fillQuery.created_after, created_before: orderQuery.created_before || fillQuery.created_before });
        downloadText(`${suffix}.json`, JSON.stringify(report, null, 2), 'application/json');
    };

    const refreshPlans = async () => {
        setLoading(true);
        try {
            const resp = await omsAPI.getPlansLatest({
                trading_mode: cfg.trading_mode,
                limit: 20,
            });
            const list = resp?.plans || [];
            setPlans(list);
            if (!planId && list[0]?.id) setPlanId(String(list[0].id));
            write(resp);
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const refreshOpportunityDetail = useCallback(
        async (opportunityId) => {
            const oid = String(opportunityId || '').trim();
            if (!oid) return;
            setOpportunityLoading(true);
            setOpportunityError('');
            try {
                const resp = await omsAPI.getOpportunity(oid, { trading_mode: cfg.trading_mode });
                setOpportunityDetail(resp?.opportunity || null);
            } catch (e) {
                setOpportunityDetail(null);
                setOpportunityError(String(e?.message || e));
            } finally {
                setOpportunityLoading(false);
            }
        },
        [cfg.trading_mode]
    );

    const refreshPlanDetail = useCallback(
        async (targetPlanId) => {
            const pid = String(targetPlanId || '').trim();
            if (!pid) return;

            setPlanDetailLoading(true);
            setPlanDetailError('');
            try {
                const resp = await omsAPI.getPlan(pid, { trading_mode: cfg.trading_mode });
                const plan = resp?.plan || null;
                setPlanDetail(plan);
                if (plan?.opportunity_id) {
                    await refreshOpportunityDetail(plan.opportunity_id);
                } else {
                    setOpportunityDetail(null);
                    setOpportunityError('');
                }
            } catch (e) {
                setPlanDetail(null);
                setPlanDetailError(String(e?.message || e));
            } finally {
                setPlanDetailLoading(false);
            }
        },
        [cfg.trading_mode, refreshOpportunityDetail]
    );

    const refreshPlanPnL = useCallback(
        async (targetPlanId) => {
            const pid = String(targetPlanId || '').trim();
            if (!pid) return;

            setPlanPnLLoading(true);
            setPlanPnLError('');
            try {
                const resp = await omsAPI.getPnLHistory({
                    trading_mode: cfg.trading_mode,
                    plan_id: pid,
                    limit: 50,
                    offset: 0,
                });
                const list = resp?.history || [];
                setPlanPnL(Array.isArray(list) ? list : []);
                setPlanPnLUpdatedAt(new Date().toISOString());
            } catch (e) {
                setPlanPnL([]);
                setPlanPnLError(String(e?.message || e));
            } finally {
                setPlanPnLLoading(false);
            }
        },
        [cfg.trading_mode]
    );

    const fetchAlerts = useCallback(async () => {
        setAlertLoading(true);
        setAlertError('');
        try {
            const params = {
                limit: alertLimit,
                offset: alertOffset,
                level: alertQuery.level || undefined,
                category: alertQuery.category || undefined,
                created_after: alertQuery.created_after || undefined,
                created_before: alertQuery.created_before || undefined,
            };
            const resp = await omsAPI.getAlerts(params);
            setAlertList(resp?.alerts || []);
            setAlertStats(resp?.stats || null);
            write(resp);
        } catch (e) {
            setAlertError(String(e?.message || e));
        } finally {
            setAlertLoading(false);
        }
    }, [alertLimit, alertOffset, alertQuery]);

    const fetchOpportunityStats = useCallback(async () => {
        setOppLoading(true);
        setOppError('');
        try {
            const params = {
                trading_mode: cfg.trading_mode,
                status: oppQuery.status || undefined,
                kind: oppQuery.kind || undefined,
            };
            const resp = await omsAPI.getOpportunityStats(params);
            setOppStats(resp?.stats || null);
            write(resp);
        } catch (e) {
            setOppStats(null);
            setOppError(String(e?.message || e));
        } finally {
            setOppLoading(false);
        }
    }, [cfg.trading_mode, oppQuery]);

    const fetchOpportunities = useCallback(async () => {
        setOppLoading(true);
        setOppError('');
        try {
            const params = {
                trading_mode: cfg.trading_mode,
                status: oppQuery.status || undefined,
                kind: oppQuery.kind || undefined,
                limit: oppQuery.limit,
            };
            const resp = await omsAPI.getOpportunities(params);
            setOppList(resp?.opportunities || []);
            write(resp);
        } catch (e) {
            setOppList([]);
            setOppError(String(e?.message || e));
        } finally {
            setOppLoading(false);
        }
    }, [cfg.trading_mode, oppQuery]);

    useEffect(() => {
        const pid = String(planId || '').trim();
        if (!pid) {
            setPlanDetail(null);
            setPlanDetailError('');
            setPlanPnL([]);
            setPlanPnLError('');
            setOpportunityDetail(null);
            setOpportunityError('');
            return;
        }
        refreshPlanDetail(pid);
        refreshPlanPnL(pid);
    }, [planId, refreshPlanDetail, refreshPlanPnL]);

    const legInsights = useMemo(() => extractLegInsights(planDetail?.legs), [planDetail?.legs]);
    const pnlSummary = legInsights?.pnlSummary?.summary || legInsights?.pnlSummary || null;

    const applySuggestedParams = () => {
        const suggested = legInsights?.suggestedRequest;
        if (!suggested || typeof suggested !== 'object') {
            alert('未找到 reconcile_suggested_request');
            return;
        }
        setCfg((c) => ({
            ...c,
            trading_mode: suggested.trading_mode ?? c.trading_mode,
            confirm_live: suggested.confirm_live ?? c.confirm_live,
            limit: suggested.limit ?? c.limit,
            max_rounds: suggested.max_rounds ?? c.max_rounds,
            sleep_ms: suggested.sleep_ms ?? c.sleep_ms,
            auto_cancel: suggested.auto_cancel ?? c.auto_cancel,
            max_age_seconds: suggested.max_age_seconds ?? c.max_age_seconds,
        }));
    };

    const executeLatest = async () => {
        setLoading(true);
        try {
            const resp = await omsAPI.executeLatest({
                trading_mode: cfg.trading_mode,
                confirm_live: !!cfg.confirm_live,
                idempotency_key: cfg.idempotency_key || null,
                limit: 1,
            });
            write(resp);
            await refreshPlans();
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const reconcile = async () => {
        if (!planId) {
            alert('请先输入计划编号');
            return;
        }
        setLoading(true);
        try {
            const resp = await omsAPI.reconcilePlan(planId, {
                trading_mode: cfg.trading_mode,
                confirm_live: !!cfg.confirm_live,
                limit: cfg.limit,
                max_rounds: cfg.max_rounds,
                sleep_ms: cfg.sleep_ms,
                auto_cancel: !!cfg.auto_cancel,
                max_age_seconds: cfg.max_age_seconds === null || String(cfg.max_age_seconds).trim() === '' ? null : Number(cfg.max_age_seconds),
            });
            write(resp);
            await refreshPlans();
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const refreshPlan = async () => {
        if (!planId) {
            alert('请先输入计划编号');
            return;
        }
        setLoading(true);
        try {
            const resp = await omsAPI.refreshPlan(planId, {
                trading_mode: cfg.trading_mode,
                confirm_live: !!cfg.confirm_live,
                limit: cfg.limit,
            });
            write(resp);
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const cancelPlan = async () => {
        if (!planId) {
            alert('请先输入计划编号');
            return;
        }
        if (!confirm('确定要取消该计划吗？')) return;
        setLoading(true);
        try {
            const resp = await omsAPI.cancelPlan(planId, {
                trading_mode: cfg.trading_mode,
                confirm_live: !!cfg.confirm_live,
                limit: cfg.limit,
            });
            write(resp);
            await refreshPlans();
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const openPlanPnL = () => {
        const pid = String(planId || '').trim();
        if (!pid) {
            alert('请先输入计划编号');
            return;
        }
        const params = new URLSearchParams({
            trading_mode: cfg.trading_mode,
            plan_id: pid,
        });
        window.location.href = `/pnl?${params.toString()}`;
    };

    const preview = async () => {
        setLoading(true);
        try {
            const resp = await omsAPI.preview(previewReq);
            write(resp);
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const previewBatch = async () => {
        setLoading(true);
        try {
            const resp = await omsAPI.previewBatch({ cases: [previewReq] });
            write(resp);
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setLoading(false);
        }
    };

    const resetOrderFilters = () => setOrderQuery(defaultOrderQuery);
    const resetFillFilters = () => setFillQuery(defaultFillQuery);

    const fetchOrders = async () => {
        setListLoading(true);
        try {
            const params = {
                trading_mode: cfg.trading_mode,
                limit: cfg.limit,
            };
            if (planId && autoRefreshPlanOnly) params.plan_id = planId;
            if (orderQuery.status) params.status = orderQuery.status;
            if (orderQuery.symbol) params.symbol = orderQuery.symbol;
            if (orderQuery.account_type) params.account_type = orderQuery.account_type;
            if (orderQuery.created_after) params.created_after = orderQuery.created_after;
            if (orderQuery.created_before) params.created_before = orderQuery.created_before;
            if (orderQuery.offset) params.offset = orderQuery.offset;
            const resp = await omsAPI.getOrders(params);
            setOrderList(resp?.orders || []);
            write(resp);
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setListLoading(false);
        }
    };

    const fetchFills = async () => {
        setListLoading(true);
        try {
            const params = { trading_mode: cfg.trading_mode, limit: cfg.limit };
            if (planId && autoRefreshPlanOnly) params.plan_id = planId;
            if (fillQuery.symbol) params.symbol = fillQuery.symbol;
            if (fillQuery.account_type) params.account_type = fillQuery.account_type;
            if (fillQuery.created_after) params.created_after = fillQuery.created_after;
            if (fillQuery.created_before) params.created_before = fillQuery.created_before;
            if (fillQuery.offset) params.offset = fillQuery.offset;
            const resp = await omsAPI.getFills(params);
            setFillList(resp?.fills || []);
            write(resp);
        } catch (e) {
            write(String(e?.message || e));
        } finally {
            setListLoading(false);
        }
    };

    useEffect(() => {
        if (planId) {
            fetchOrders();
            fetchFills();
        }
    }, [planId, cfg.trading_mode, autoRefreshPlanOnly]);

    useEffect(() => {
        setOrderQuery((s) => ({ ...s, offset: 0 }));
        setFillQuery((s) => ({ ...s, offset: 0 }));
    }, [planId, autoRefreshPlanOnly]);

    useEffect(() => {
        if (!autoRefresh) return;
        const interval = Math.max(1000, Number(autoRefreshMs) || 5000);
        const timer = setInterval(() => {
            fetchOrders();
            fetchFills();
            if (planId && autoRefreshPlanPnL) {
                refreshPlanPnL(planId);
            }
        }, interval);
        return () => clearInterval(timer);
    }, [autoRefresh, autoRefreshMs, planId, cfg.trading_mode, orderQuery, fillQuery, autoRefreshPlanOnly, autoRefreshPlanPnL, refreshPlanPnL]);

    const saveDefaults = () => {
        try {
            const normalized = normalizeConfig(cfg);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
            setCfg((c) => ({ ...c, ...normalized }));
            setDefaultsSavedAt(new Date());
            alert('订单管理默认参数已保存到本地');
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    const loadDefaults = () => {
        try {
            const normalized = normalizeConfig(loadConfig() || defaultConfig());
            setCfg((c) => ({ ...c, ...normalized }));
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    const resetDefaults = () => {
        if (!confirm('确定要重置订单管理默认参数吗？')) return;
        try {
            const d = normalizeConfig(defaultConfig());
            localStorage.setItem(STORAGE_KEY, JSON.stringify(d));
            setCfg((c) => ({ ...c, ...d }));
            setDefaultsSavedAt(new Date());
        } catch (e) {
            alert(String(e?.message || e));
        }
    };

    return (
        <div className="content-body">
            <div className="page-header" style={{ marginBottom: '16px' }}>
                <div>
                    <h1 className="page-title">订单管理控制</h1>
                    <p className="page-subtitle">执行 / 对账 / 撤单 / 刷新 / 下一步动作预览</p>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div className="card">
                    <div className="card-header"><span className="card-title">⚙️ 参数</span></div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>交易模式</label>
                                <select value={cfg.trading_mode} onChange={(e) => setCfg({ ...cfg, trading_mode: e.target.value })}
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}>
                                    <option value="paper">🟢 模拟</option>
                                    <option value="live">🔴 实盘</option>
                                </select>
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>实盘确认开关</label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83', marginTop: '6px' }}>
                                    <input type="checkbox" checked={!!cfg.confirm_live} onChange={(e) => setCfg({ ...cfg, confirm_live: e.target.checked })} />
                                    实盘确认
                                </label>
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>幂等键（实盘必填）</label>
                                <input
                                    value={cfg.idempotency_key ?? ''}
                                    onChange={(e) => setCfg({ ...cfg, idempotency_key: e.target.value })}
                                    placeholder="例如: live-2026-01-30-001"
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                                />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>执行条数</label>
                                <input type="number" value={cfg.limit} onChange={(e) => setCfg({ ...cfg, limit: Number(e.target.value) })}
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }} />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>最大轮数</label>
                                <input type="number" value={cfg.max_rounds} onChange={(e) => setCfg({ ...cfg, max_rounds: Number(e.target.value) })}
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }} />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>轮询间隔（毫秒）</label>
                                <input type="number" value={cfg.sleep_ms} onChange={(e) => setCfg({ ...cfg, sleep_ms: Number(e.target.value) })}
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }} />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>最大计划时长（秒）</label>
                                <input type="number" value={cfg.max_age_seconds ?? ''} onChange={(e) => setCfg({ ...cfg, max_age_seconds: e.target.value === '' ? null : Number(e.target.value) })}
                                    placeholder="留空表示不启用"
                                    style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }} />
                            </div>
                            <div style={{ gridColumn: '1 / span 2' }}>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>自动撤单（危险）</label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83', marginTop: '6px' }}>
                                    <input type="checkbox" checked={!!cfg.auto_cancel} onChange={(e) => setCfg({ ...cfg, auto_cancel: e.target.checked })} />
                                    对账超时/轮询耗尽后自动撤单
                                </label>
                            </div>
                        </div>

                        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '12px' }}>
                            <button className="btn btn-secondary btn-sm" onClick={loadDefaults}>加载默认</button>
                            <button className="btn btn-secondary btn-sm" onClick={resetDefaults}>重置默认</button>
                            <button className="btn btn-primary btn-sm" onClick={saveDefaults}>保存为默认</button>
                        </div>
                        <div style={{ marginTop: '8px', fontSize: '9px', color: 'var(--text-muted)' }}>
                            {defaultsSavedAt ? `最近保存：${defaultsSavedAt.toLocaleString()}` : '提示：默认参数保存在本地（localStorage），用于下次进入自动加载'}
                        </div>
                    </div>
                </div>

                <div className="card">
                    <div className="card-header"><span className="card-title">🧾 执行计划</span></div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                            <input
                                value={planId}
                                onChange={(e) => setPlanId(e.target.value)}
                                placeholder="计划编号"
                                style={{ flex: 1, padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <button className="btn btn-secondary btn-sm" onClick={refreshPlans} disabled={loading}>拉取计划</button>
                            <button className="btn btn-secondary btn-sm" onClick={() => refreshPlanDetail(planId)} disabled={loading || planDetailLoading}>拉取详情</button>
                        </div>

                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            <button className="btn btn-primary btn-sm" onClick={executeLatest} disabled={loading}>执行最新</button>
                            <button className="btn btn-secondary btn-sm" onClick={refreshPlan} disabled={loading}>刷新计划</button>
                            <button className="btn btn-primary btn-sm" onClick={reconcile} disabled={loading}>对账</button>
                            <button className="btn btn-danger btn-sm" onClick={cancelPlan} disabled={loading}>取消计划</button>
                            <button className="btn btn-secondary btn-sm" onClick={openPlanPnL}>查看收益</button>
                            <button className="btn btn-secondary btn-sm" onClick={() => exportCurrentPlan('json')}>导出当前计划数据</button>
                            <button className="btn btn-secondary btn-sm" onClick={() => exportCurrentPlan('csv')}>导出当前计划表格</button>
                        </div>

                        <div style={{ marginTop: '10px', maxHeight: '160px', overflow: 'auto', fontSize: '10px' }}>
                            {(plans || []).slice(0, 10).map((p) => (
                                <div key={p.id} style={{ padding: '6px', borderBottom: '1px solid rgba(0,0,0,0.05)', cursor: 'pointer' }} onClick={() => setPlanId(String(p.id))}>
                                    <div style={{ fontWeight: 700 }}>{String(p.id).slice(0, 8)}... <span style={{ color: 'var(--text-muted)' }}>{getStatusLabel(p.status)}</span></div>
                                    <div style={{ color: 'var(--text-muted)' }}>{getPlanKindLabel(p.kind)} · {p.created_at}</div>
                                </div>
                            ))}
                            {(!plans || plans.length === 0) && (
                                <div style={{ color: 'var(--text-muted)' }}>暂无计划，点“拉取计划”</div>
                            )}
                        </div>
                        <div style={{ marginTop: '10px', padding: '8px', background: 'rgba(0,0,0,0.03)', borderRadius: '6px', fontSize: '9px', color: 'var(--text-muted)' }}>
                            <div style={{ fontWeight: 700, marginBottom: '6px' }}>当前计划统计</div>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                <span>订单数: {orderListSummary.total}</span>
                                <span>成交数: {fillListSummary.total}</span>
                                <span>粗略收益: {fillListSummary.roughPnL}</span>
                                {pnlSummary && pnlSummary.profit && (
                                    <span>收益: {String(pnlSummary.profit)}</span>
                                )}
                                {pnlSummary && pnlSummary.profit_rate && (
                                    <span>收益率: {String(pnlSummary.profit_rate)}</span>
                                )}
                                {pnlSummary && pnlSummary.total_fee && (
                                    <span>手续费: {String(pnlSummary.total_fee)}</span>
                                )}
                                {pnlSummary && pnlSummary.quote_currency && (
                                    <span>计价币: {String(pnlSummary.quote_currency)}</span>
                                )}
                                {pnlSummary && pnlSummary.total_notional && (
                                    <span>名义金额: {String(pnlSummary.total_notional)}</span>
                                )}
                            </div>
                            {Object.keys(orderListSummary.statusCounts).length > 0 && (
                                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '6px' }}>
                                    {Object.keys(orderListSummary.statusCounts).map((k) => (
                                        <span key={k} style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                            {getStatusLabel(k)}: {orderListSummary.statusCounts[k]}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div style={{ marginTop: '10px', padding: '8px', background: 'rgba(0,0,0,0.03)', borderRadius: '6px', fontSize: '9px', color: 'var(--text-muted)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                <div style={{ fontWeight: 700 }}>当前计划收益</div>
                                <div style={{ display: 'flex', gap: '6px' }}>
                                    <button className="btn btn-secondary btn-sm" onClick={() => refreshPlanPnL(planId)} disabled={planPnLLoading}>刷新</button>
                                    <button className="btn btn-secondary btn-sm" onClick={() => exportPlanPnL('csv')} disabled={!planPnL?.length}>导出表格</button>
                                    <button className="btn btn-secondary btn-sm" onClick={() => exportPlanPnL('json')} disabled={!planPnL?.length}>导出数据</button>
                                    <button className="btn btn-secondary btn-sm" onClick={exportPlanPnLReport} disabled={!planPnL?.length}>导出报告</button>
                                </div>
                            </div>
                            {planPnLUpdatedAt && (
                                <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                                    最后更新: {planPnLUpdatedAt}
                                </div>
                            )}
                            {!planId && <div>请先输入计划编号</div>}
                            {planId && planPnLLoading && <div>加载中...</div>}
                            {planId && !planPnLLoading && planPnLError && (
                                <div style={{ color: '#dc322f', whiteSpace: 'pre-wrap' }}>{planPnLError}</div>
                            )}
                            {planId && !planPnLLoading && !planPnLError && (!planPnL || planPnL.length === 0) && (
                                <div>暂无收益记录</div>
                            )}
                            {planId && !planPnLLoading && !planPnLError && planPnL.length > 0 && (
                                <div style={{ display: 'grid', gap: '6px' }}>
                                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                        <span>笔数: {planPnLSummary.total}</span>
                                        <span>总收益: {planPnLSummary.totalProfit.toFixed(6)}</span>
                                        <span>平均收益: {planPnLSummary.avgProfit.toFixed(6)}</span>
                                        <span>胜率: {(planPnLSummary.winRate * 100).toFixed(2)}%</span>
                                        <span>振幅: {planPnLRiskMetrics.range.toFixed(6)}</span>
                                        <span>最大回撤: {planPnLRiskMetrics.maxDrawdown.toFixed(6)}</span>
                                        <span>分位10: {planPnLQuantiles.p10.toFixed(6)}</span>
                                        <span>分位50: {planPnLQuantiles.p50.toFixed(6)}</span>
                                        <span>分位90: {planPnLQuantiles.p90.toFixed(6)}</span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                                        <span>时间窗口</span>
                                        <button className="btn btn-secondary btn-sm" onClick={() => setPlanPnLWindow('5m')} disabled={planPnLWindow === '5m'}>5分钟</button>
                                        <button className="btn btn-secondary btn-sm" onClick={() => setPlanPnLWindow('15m')} disabled={planPnLWindow === '15m'}>15分钟</button>
                                        <button className="btn btn-secondary btn-sm" onClick={() => setPlanPnLWindow('1h')} disabled={planPnLWindow === '1h'}>1小时</button>
                                    </div>
                                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                                        <span>阶段标记</span>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <input type="checkbox" checked={planMarkerFilter.execution} onChange={(e) => setPlanMarkerFilter((s) => ({ ...s, execution: e.target.checked }))} />
                                            执行
                                        </label>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <input type="checkbox" checked={planMarkerFilter.reconcile} onChange={(e) => setPlanMarkerFilter((s) => ({ ...s, reconcile: e.target.checked }))} />
                                            对账
                                        </label>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <input type="checkbox" checked={planMarkerFilter.pnl} onChange={(e) => setPlanMarkerFilter((s) => ({ ...s, pnl: e.target.checked }))} />
                                            收益
                                        </label>
                                    </div>
                                    <div style={{ height: '120px', marginTop: '6px' }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={planPnLWindowBuckets} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                                                <Bar dataKey="value" fill="var(--cyan)" />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <div style={{ height: '120px', marginTop: '6px' }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={planPnLChart} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                                                {filteredPlanStageMarkers.map((m, idx) => (
                                                    <ReferenceLine key={`${m.time}-${idx}`} x={m.time} stroke="rgba(220, 50, 47, 0.4)" label={{ value: m.label, fontSize: 8, fill: '#dc322f' }} />
                                                ))}
                                                <Line type="monotone" dataKey="value" stroke="var(--cyan)" strokeWidth={2} dot={{ r: 1 }} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <div style={{ height: '120px', marginTop: '6px' }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={planPnLDrawdownCurve} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                                                {filteredPlanStageMarkers.map((m, idx) => (
                                                    <ReferenceLine key={`${m.time}-${idx}-dd`} x={m.time} stroke="rgba(220, 50, 47, 0.35)" />
                                                ))}
                                                <Line type="monotone" dataKey="equity" stroke="var(--color-profit)" strokeWidth={2} dot={false} />
                                                <Line type="monotone" dataKey="drawdown" stroke="var(--color-loss)" strokeWidth={2} dot={false} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <div style={{ display: 'grid', gap: '4px' }}>
                                        <div style={{ fontWeight: 700 }}>单笔收益分布</div>
                                        <div style={{ height: '120px' }}>
                                            <ResponsiveContainer width="100%" height="100%">
                                                <BarChart data={planPnLDistribution} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                                    <XAxis dataKey="bucket" tick={{ fontSize: 8 }} stroke="var(--text-muted)" />
                                                    <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                    <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                                                    <Bar dataKey="count" fill="var(--color-profit)" />
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </div>
                                        {!planPnLDistribution.length && <div>暂无数据</div>}
                                    </div>
                                    <div style={{ display: 'grid', gap: '4px' }}>
                                        <div style={{ fontWeight: 700 }}>按交易对收益</div>
                                        <div style={{ height: '120px' }}>
                                            <ResponsiveContainer width="100%" height="100%">
                                                <BarChart data={planPnLSymbols.slice(0, 6).map(([sym, profit]) => ({ symbol: sym, value: Number(profit.toFixed(6)) }))} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                                    <XAxis dataKey="symbol" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                    <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                    <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                                                    <Bar dataKey="value" fill="var(--color-profit)" />
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </div>
                                        {!planPnLSymbols.length && <div>暂无数据</div>}
                                    </div>
                                    <div style={{ display: 'grid', gap: '4px' }}>
                                        <div style={{ fontWeight: 700 }}>按交易所收益</div>
                                        <div style={{ height: '120px' }}>
                                            <ResponsiveContainer width="100%" height="100%">
                                                <BarChart data={planPnLExchangeBreakdown.slice(0, 6).map(([name, profit]) => ({ exchange: name, value: Number(profit.toFixed(6)) }))} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                                                    <XAxis dataKey="exchange" tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                    <YAxis tick={{ fontSize: 9 }} stroke="var(--text-muted)" />
                                                    <Tooltip contentStyle={{ backgroundColor: 'var(--base3)', border: '1px solid var(--border-subtle)', fontSize: '10px' }} />
                                                    <Bar dataKey="value" fill="var(--color-profit)" />
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </div>
                                        {!planPnLExchangeBreakdown.length && <div>暂无数据</div>}
                                    </div>
                                    {planPnL.slice(0, 5).map((row) => (
                                        <div key={row.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                                            <span>{row.symbol || '多币种'}</span>
                                            <span>{row.profit >= 0 ? '+' : ''}{Number(row.profit || 0).toFixed(6)}</span>
                                            <span>{row.profit_rate !== null && row.profit_rate !== undefined ? `${(Number(row.profit_rate) * 100).toFixed(2)}%` : '—'}</span>
                                            <span>{row.created_at ? String(row.created_at).slice(0, 19) : '—'}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            <div className="card" style={{ marginBottom: '12px' }}>
                <div className="card-header"><span className="card-title">🚨 告警历史</span></div>
                <div className="card-body" style={{ padding: '12px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>条数</label>
                            <input
                                type="number"
                                value={alertLimit}
                                onChange={(e) => setAlertLimit(Number(e.target.value))}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>偏移</label>
                            <input
                                type="number"
                                value={alertOffset}
                                onChange={(e) => setAlertOffset(Number(e.target.value))}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div style={{ fontSize: '9px', color: 'var(--text-muted)' }}>
                            {alertLoading ? '加载中...' : `共 ${alertList.length} 条`}
                        </div>
                        <button className="btn btn-secondary btn-sm" onClick={fetchAlerts} disabled={alertLoading}>拉取告警</button>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '8px', marginBottom: '8px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>等级</label>
                            <select
                                value={alertQuery.level}
                                onChange={(e) => setAlertQuery({ ...alertQuery, level: e.target.value })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            >
                                <option value="">全部</option>
                                <option value="info">INFO</option>
                                <option value="warn">WARN</option>
                                <option value="error">ERROR</option>
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>类别</label>
                            <input
                                value={alertQuery.category}
                                onChange={(e) => setAlertQuery({ ...alertQuery, category: e.target.value })}
                                placeholder="risk/latency/order_failure"
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>开始时间</label>
                            <input
                                type="datetime-local"
                                value={alertQuery.created_after}
                                onChange={(e) => setAlertQuery({ ...alertQuery, created_after: e.target.value })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>结束时间</label>
                            <input
                                type="datetime-local"
                                value={alertQuery.created_before}
                                onChange={(e) => setAlertQuery({ ...alertQuery, created_before: e.target.value })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                    </div>
                    {!alertError && alertStats && (
                        <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                            等级: {Object.entries(alertStats.by_level || {}).map(([k, v]) => `${k}:${v}`).join(' ')} ·
                            类别: {Object.entries(alertStats.by_category || {}).map(([k, v]) => `${k}:${v}`).join(' ')}
                        </div>
                    )}
                    {alertError && <div style={{ color: '#dc322f', whiteSpace: 'pre-wrap' }}>{alertError}</div>}
                    {!alertError && (
                        <div style={{ maxHeight: '200px', overflow: 'auto', fontSize: '10px' }}>
                            {alertList.length === 0 && <div style={{ color: 'var(--text-muted)' }}>暂无告警记录</div>}
                            {alertList.map((a, idx) => (
                                <div key={idx} style={{ padding: '6px', borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
                                    <div style={{ fontWeight: 700 }}>{String(a.level || 'INFO')} · {String(a.category || '-')}</div>
                                    <div style={{ color: 'var(--text-muted)' }}>{String(a.message || '')}</div>
                                    <div style={{ color: 'var(--text-muted)' }}>{String(a.created_at || '')}</div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <div className="card" style={{ marginBottom: '12px' }}>
                <div className="card-header"><span className="card-title">🎯 机会统计与筛选</span></div>
                <div className="card-body" style={{ padding: '12px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>状态</label>
                            <input
                                value={oppQuery.status}
                                onChange={(e) => setOppQuery({ ...oppQuery, status: e.target.value })}
                                placeholder="accepted/executed/rejected"
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>类型</label>
                            <input
                                value={oppQuery.kind}
                                onChange={(e) => setOppQuery({ ...oppQuery, kind: e.target.value })}
                                placeholder="triangle/basis/funding"
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>条数</label>
                            <input
                                type="number"
                                value={oppQuery.limit}
                                onChange={(e) => setOppQuery({ ...oppQuery, limit: Number(e.target.value) })}
                                style={{ width: '100%', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                        </div>
                        <div style={{ display: 'flex', gap: '6px' }}>
                            <button className="btn btn-secondary btn-sm" onClick={fetchOpportunityStats} disabled={oppLoading}>统计</button>
                            <button className="btn btn-secondary btn-sm" onClick={fetchOpportunities} disabled={oppLoading}>拉取列表</button>
                        </div>
                    </div>
                    {oppError && <div style={{ color: '#dc322f', whiteSpace: 'pre-wrap' }}>{oppError}</div>}
                    {!oppError && oppStats && (
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                            总数: {oppStats.total ?? 0} ·
                            状态: {Object.entries(oppStats.by_status || {}).map(([k, v]) => `${k}:${v}`).join(' ')} ·
                            类型: {Object.entries(oppStats.by_kind || {}).map(([k, v]) => `${k}:${v}`).join(' ')}
                        </div>
                    )}
                    {!oppError && (
                        <div style={{ maxHeight: '200px', overflow: 'auto', fontSize: '10px' }}>
                            {oppList.length === 0 && <div style={{ color: 'var(--text-muted)' }}>暂无机会记录</div>}
                            {oppList.map((o) => (
                                <div key={o.id} style={{ padding: '6px', borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
                                    <div style={{ fontWeight: 700 }}>{String(o.kind || '-')} · {String(o.status || '-')}</div>
                                    <div style={{ color: 'var(--text-muted)' }}>{String(o.id)}</div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div className="card">
                    <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                        <span className="card-title">📦 订单列表</span>
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                            <input
                                value={orderQuery.symbol}
                                onChange={(e) => setOrderQuery((s) => ({ ...s, symbol: e.target.value }))}
                                placeholder="交易对"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={orderQuery.status}
                                onChange={(e) => setOrderQuery((s) => ({ ...s, status: e.target.value }))}
                                placeholder="状态"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={orderQuery.account_type}
                                onChange={(e) => setOrderQuery((s) => ({ ...s, account_type: e.target.value }))}
                                placeholder="账户类型"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={orderQuery.created_after}
                                onChange={(e) => setOrderQuery((s) => ({ ...s, created_after: e.target.value }))}
                                placeholder="开始时间（标准格式）"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={orderQuery.created_before}
                                onChange={(e) => setOrderQuery((s) => ({ ...s, created_before: e.target.value }))}
                                placeholder="结束时间（标准格式）"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                type="number"
                                value={orderQuery.offset}
                                onChange={(e) => setOrderQuery((s) => ({ ...s, offset: Number(e.target.value) }))}
                                placeholder="偏移量"
                                style={{ width: '80px', padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <button className="btn btn-secondary btn-sm" onClick={fetchOrders} disabled={listLoading}>拉取订单</button>
                            <button className="btn btn-secondary btn-sm" onClick={resetOrderFilters}>清空过滤</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => downloadText(`${buildExportSuffix('orders', orderQuery)}.json`, JSON.stringify(orderList, null, 2), 'application/json')}
                                disabled={!orderList.length}
                            >导出数据</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const csv = toCsv(orderList, [
                                        { key: 'created_at', label: '创建时间' },
                                        { key: 'status', label: '状态' },
                                        { key: 'id', label: '订单编号' },
                                        { key: 'symbol', label: '交易对' },
                                        { key: 'side', label: '方向' },
                                        { key: 'plan_id', label: '计划编号' },
                                        { key: 'filled_quantity', label: '成交数量' },
                                        { key: 'average_price', label: '成交均价' },
                                    ]);
                                    downloadText(`${buildExportSuffix('orders', orderQuery)}.csv`, csv, 'text/csv');
                                }}
                                disabled={!orderList.length}
                            >导出表格</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => downloadText(`${buildExportSuffix('orders_filtered', orderQuery)}.json`, JSON.stringify(orderList, null, 2), 'application/json')}
                                disabled={!orderList.length}
                            >导出筛选数据</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const csv = toCsv(orderList, [
                                        { key: 'created_at', label: '创建时间' },
                                        { key: 'status', label: '状态' },
                                        { key: 'id', label: '订单编号' },
                                        { key: 'symbol', label: '交易对' },
                                        { key: 'side', label: '方向' },
                                        { key: 'plan_id', label: '计划编号' },
                                        { key: 'filled_quantity', label: '成交数量' },
                                        { key: 'average_price', label: '成交均价' },
                                    ]);
                                    downloadText(`${buildExportSuffix('orders_filtered', orderQuery)}.csv`, csv, 'text/csv');
                                }}
                                disabled={!orderList.length}
                            >导出筛选表格</button>
                        </div>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                                <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
                                自动刷新
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                                <input type="checkbox" checked={autoRefreshPlanOnly} onChange={(e) => setAutoRefreshPlanOnly(e.target.checked)} />
                                仅当前计划
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                                <input type="checkbox" checked={autoRefreshPlanPnL} onChange={(e) => setAutoRefreshPlanPnL(e.target.checked)} />
                                同步计划收益
                            </label>
                            <input
                                type="number"
                                value={autoRefreshMs}
                                onChange={(e) => setAutoRefreshMs(Number(e.target.value))}
                                style={{ width: '90px', padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                                placeholder="毫秒"
                            />
                        </div>
                        <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const now = new Date();
                                    const start = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
                                    setOrderQuery((s) => ({ ...s, created_after: start, created_before: now.toISOString(), offset: 0 }));
                                }}
                            >最近 1小时</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const now = new Date();
                                    const start = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
                                    setOrderQuery((s) => ({ ...s, created_after: start, created_before: now.toISOString(), offset: 0 }));
                                }}
                            >最近 24小时</button>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px', flexWrap: 'wrap' }}>
                            <span>总数: {orderListSummary.total}</span>
                            {Object.keys(orderListSummary.statusCounts).map((k) => (
                                <span key={k} style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                    {getStatusLabel(k)}: {orderListSummary.statusCounts[k]}
                                </span>
                            ))}
                        </div>
                        {!orderList.length && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无订单</div>}
                        {orderList.length > 0 && (
                            <>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        onClick={() => setOrderQuery((s) => ({ ...s, offset: Math.max(0, (Number(s.offset) || 0) - cfg.limit) }))}
                                    >上一页</button>
                                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>偏移: {orderQuery.offset || 0}</div>
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        onClick={() => setOrderQuery((s) => ({ ...s, offset: (Number(s.offset) || 0) + cfg.limit }))}
                                    >下一页</button>
                                </div>
                                <div style={{ maxHeight: '240px', overflow: 'auto' }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: '120px 70px 1fr 80px 80px 1fr', gap: '8px', fontSize: '9px', fontWeight: 700, marginBottom: '6px' }}>
                                        <div>时间</div>
                                        <div>状态</div>
                                        <div>订单编号</div>
                                        <div>交易对</div>
                                        <div>方向</div>
                                        <div>计划编号</div>
                                    </div>
                                    {orderList.map((o) => (
                                        <div
                                            key={o.id}
                                            style={{
                                                display: 'grid',
                                                gridTemplateColumns: '120px 70px 1fr 80px 80px 1fr',
                                                gap: '8px',
                                                fontSize: '9px',
                                                padding: '6px 0',
                                                borderBottom: '1px solid rgba(0,0,0,0.05)'
                                            }}
                                        >
                                            <div style={{ color: 'var(--text-muted)' }}>{o.created_at}</div>
                                            <div>{getStatusLabel(o.status) || '-'}</div>
                                            <div style={{ fontFamily: 'monospace' }}>{o.id}</div>
                                            <div>{o.symbol || '-'}</div>
                                            <div>{getSideLabel(o.side) || '-'}</div>
                                            <div style={{ fontFamily: 'monospace' }}>{o.plan_id || '-'}</div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </div>
                <div className="card">
                    <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                        <span className="card-title">✅ 成交列表</span>
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                            <input
                                value={fillQuery.symbol}
                                onChange={(e) => setFillQuery((s) => ({ ...s, symbol: e.target.value }))}
                                placeholder="交易对"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={fillQuery.account_type}
                                onChange={(e) => setFillQuery((s) => ({ ...s, account_type: e.target.value }))}
                                placeholder="账户类型"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={fillQuery.created_after}
                                onChange={(e) => setFillQuery((s) => ({ ...s, created_after: e.target.value }))}
                                placeholder="开始时间（标准格式）"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                value={fillQuery.created_before}
                                onChange={(e) => setFillQuery((s) => ({ ...s, created_before: e.target.value }))}
                                placeholder="结束时间（标准格式）"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <input
                                type="number"
                                value={fillQuery.offset}
                                onChange={(e) => setFillQuery((s) => ({ ...s, offset: Number(e.target.value) }))}
                                placeholder="偏移量"
                                style={{ width: '80px', padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <button className="btn btn-secondary btn-sm" onClick={fetchFills} disabled={listLoading}>拉取成交</button>
                            <button className="btn btn-secondary btn-sm" onClick={resetFillFilters}>清空过滤</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => downloadText(`${buildExportSuffix('fills', fillQuery)}.json`, JSON.stringify(fillList, null, 2), 'application/json')}
                                disabled={!fillList.length}
                            >导出数据</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const csv = toCsv(fillList, [
                                        { key: 'created_at', label: '创建时间' },
                                        { key: 'id', label: '成交编号' },
                                        { key: 'order_id', label: '订单编号' },
                                        { key: 'symbol', label: '交易对' },
                                        { key: 'quantity', label: '数量' },
                                        { key: 'price', label: '价格' },
                                        { key: 'fee', label: '手续费' },
                                        { key: 'fee_currency', label: '手续费币种' },
                                    ]);
                                    downloadText(`${buildExportSuffix('fills', fillQuery)}.csv`, csv, 'text/csv');
                                }}
                                disabled={!fillList.length}
                            >导出表格</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => downloadText(`${buildExportSuffix('fills_filtered', fillQuery)}.json`, JSON.stringify(fillList, null, 2), 'application/json')}
                                disabled={!fillList.length}
                            >导出筛选数据</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const csv = toCsv(fillList, [
                                        { key: 'created_at', label: '创建时间' },
                                        { key: 'id', label: '成交编号' },
                                        { key: 'order_id', label: '订单编号' },
                                        { key: 'symbol', label: '交易对' },
                                        { key: 'quantity', label: '数量' },
                                        { key: 'price', label: '价格' },
                                        { key: 'fee', label: '手续费' },
                                        { key: 'fee_currency', label: '手续费币种' },
                                    ]);
                                    downloadText(`${buildExportSuffix('fills_filtered', fillQuery)}.csv`, csv, 'text/csv');
                                }}
                                disabled={!fillList.length}
                            >导出筛选表格</button>
                        </div>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const now = new Date();
                                    const start = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
                                    setFillQuery((s) => ({ ...s, created_after: start, created_before: now.toISOString(), offset: 0 }));
                                }}
                            >最近 1小时</button>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                    const now = new Date();
                                    const start = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
                                    setFillQuery((s) => ({ ...s, created_after: start, created_before: now.toISOString(), offset: 0 }));
                                }}
                            >最近 24小时</button>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px', flexWrap: 'wrap' }}>
                            <span>总数: {fillListSummary.total}</span>
                            <span>手续费: {fillListSummary.totalFee}</span>
                            <span>手续费币种: {fillListSummary.feeCurrencies}</span>
                        </div>
                        {fillListSummary.total > 0 && (
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                                {Object.keys(fillListSummary.bySymbol).map((sym) => (
                                    <span key={sym} style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                        {sym}: {Number(fillListSummary.bySymbol[sym] || 0).toFixed(4)}
                                    </span>
                                ))}
                            </div>
                        )}
                        {fillListSummary.total > 0 && (
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                                {Object.keys(fillListSummary.byAccount).map((acct) => (
                                    <span key={acct} style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                        {getAccountLabel(acct)}: {Number(fillListSummary.byAccount[acct] || 0).toFixed(4)}
                                    </span>
                                ))}
                            </div>
                        )}
                        {fillListSummary.total > 0 && (
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                                <span style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                    买入数量: {fillListSummary.bySide.buy_qty.toFixed(4)}
                                </span>
                                <span style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                    卖出数量: {fillListSummary.bySide.sell_qty.toFixed(4)}
                                </span>
                                <span style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                    买入名义: {fillListSummary.bySide.buy_notional.toFixed(4)}
                                </span>
                                <span style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                    卖出名义: {fillListSummary.bySide.sell_notional.toFixed(4)}
                                </span>
                                <span style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                    粗略收益估计: {fillListSummary.roughPnL}
                                </span>
                            </div>
                        )}
                        {!fillList.length && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无成交</div>}
                        {fillList.length > 0 && (
                            <>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        onClick={() => setFillQuery((s) => ({ ...s, offset: Math.max(0, (Number(s.offset) || 0) - cfg.limit) }))}
                                    >上一页</button>
                                    <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>偏移: {fillQuery.offset || 0}</div>
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        onClick={() => setFillQuery((s) => ({ ...s, offset: (Number(s.offset) || 0) + cfg.limit }))}
                                    >下一页</button>
                                </div>
                                <div style={{ maxHeight: '240px', overflow: 'auto' }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr 80px 80px 60px 60px', gap: '8px', fontSize: '9px', fontWeight: 700, marginBottom: '6px' }}>
                                        <div>时间</div>
                                        <div>成交编号</div>
                                        <div>交易对</div>
                                        <div>数量</div>
                                        <div>价格</div>
                                        <div>手续费</div>
                                    </div>
                                    {fillList.map((f) => (
                                        <div
                                            key={f.id}
                                            style={{
                                                display: 'grid',
                                                gridTemplateColumns: '120px 1fr 80px 80px 60px 60px',
                                                gap: '8px',
                                                fontSize: '9px',
                                                padding: '6px 0',
                                                borderBottom: '1px solid rgba(0,0,0,0.05)'
                                            }}
                                        >
                                            <div style={{ color: 'var(--text-muted)' }}>{f.created_at}</div>
                                            <div style={{ fontFamily: 'monospace' }}>{f.id}</div>
                                            <div>{f.symbol || '-'}</div>
                                            <div>{f.quantity ?? '-'}</div>
                                            <div>{f.price ?? '-'}</div>
                                            <div>{f.fee ?? '-'}</div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div className="card">
                    <div className="card-header"><span className="card-title">🧩 分腿摘要</span></div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        {!planId && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>请先输入计划编号</div>}
                        {planId && planDetailLoading && <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>加载中...</div>}
                        {planId && !planDetailLoading && planDetailError && (
                            <div style={{ color: '#dc322f', fontSize: '10px', whiteSpace: 'pre-wrap' }}>{planDetailError}</div>
                        )}
                        {planId && !planDetailLoading && !planDetailError && !planDetail && (
                            <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>未找到计划</div>
                        )}
                        {planDetail && (
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '10px' }}>
                                <div>
                                    <div style={{ fontWeight: 700 }}>计划状态</div>
                                    <div style={{ color: 'var(--text-muted)' }}>{getStatusLabel(planDetail.status)}</div>
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700 }}>计划类型</div>
                                    <div style={{ color: 'var(--text-muted)' }}>{getPlanKindLabel(planDetail.kind)}</div>
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700 }}>分腿数量</div>
                                    <div style={{ color: 'var(--text-muted)' }}>{Array.isArray(planDetail.legs) ? planDetail.legs.length : 0}</div>
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700 }}>错误信息</div>
                                    <div style={{ color: planDetail.error_message ? '#dc322f' : 'var(--text-muted)', whiteSpace: 'pre-wrap' }}>{String(planDetail.error_message || '')}</div>
                                </div>

                                <div style={{ gridColumn: '1 / span 2' }}>
                                    <div style={{ fontWeight: 700, marginBottom: '6px' }}>关联机会</div>
                                    {!planDetail.opportunity_id && <div style={{ color: 'var(--text-muted)' }}>暂无关联机会</div>}
                                    {planDetail.opportunity_id && opportunityLoading && <div style={{ color: 'var(--text-muted)' }}>加载中...</div>}
                                    {planDetail.opportunity_id && !opportunityLoading && opportunityError && (
                                        <div style={{ color: '#dc322f', whiteSpace: 'pre-wrap' }}>{opportunityError}</div>
                                    )}
                                    {planDetail.opportunity_id && !opportunityLoading && !opportunityError && opportunityDetail && (
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '10px' }}>
                                            <div>
                                                <div style={{ color: 'var(--text-muted)' }}>机会编号</div>
                                                <div>{String(opportunityDetail.id)}</div>
                                            </div>
                                            <div>
                                                <div style={{ color: 'var(--text-muted)' }}>机会状态</div>
                                                <div>{String(opportunityDetail.status || '-')}</div>
                                            </div>
                                            <div>
                                                <div style={{ color: 'var(--text-muted)' }}>类型</div>
                                                <div>{String(opportunityDetail.kind || '-')}</div>
                                            </div>
                                            <div>
                                                <div style={{ color: 'var(--text-muted)' }}>期望收益</div>
                                                <div>{String(opportunityDetail.expected_pnl ?? '-')}</div>
                                            </div>
                                            <div>
                                                <div style={{ color: 'var(--text-muted)' }}>容量</div>
                                                <div>{String(opportunityDetail.capacity ?? '-')}</div>
                                            </div>
                                            <div>
                                                <div style={{ color: 'var(--text-muted)' }}>评分</div>
                                                <div>{String(opportunityDetail.score ?? '-')}</div>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div style={{ gridColumn: '1 / span 2' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '6px' }}>
                                        <div style={{ fontWeight: 700 }}>对账建议请求</div>
                                        <button className="btn btn-primary btn-sm" onClick={applySuggestedParams} disabled={!legInsights?.suggestedRequest}>一键填充参数</button>
                                    </div>
                                    <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '180px', overflow: 'auto' }}>
                                        {legInsights?.suggestedRequest ? safeJson(legInsights.suggestedRequest) : '无'}
                                    </pre>
                                </div>

                                <div>
                                    <div style={{ fontWeight: 700, marginBottom: '6px' }}>执行摘要</div>
                                    <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '180px', overflow: 'auto' }}>
                                        {legInsights?.executionSummary ? safeJson(legInsights.executionSummary) : '无'}
                                    </pre>
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700, marginBottom: '6px' }}>分腿对账建议请求</div>
                                    <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '180px', overflow: 'auto' }}>
                                        {legInsights?.reconcileSuggested ? safeJson(legInsights.reconcileSuggested) : '无'}
                                    </pre>
                                </div>
                                <div style={{ gridColumn: '1 / span 2' }}>
                                    <div style={{ fontWeight: 700, marginBottom: '6px' }}>收益摘要</div>
                                    <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '180px', overflow: 'auto' }}>
                                        {legInsights?.pnlSummary ? safeJson(legInsights.pnlSummary) : '无'}
                                    </pre>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <div className="card">
                    <div className="card-header"><span className="card-title">🧾 计划原始数据（含分腿）</span></div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '360px', overflow: 'auto' }}>
                            {planDetail ? safeJson(planDetail) : '暂无'}
                        </pre>
                    </div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div className="card">
                    <div className="card-header"><span className="card-title">🧪 下一步动作预览</span></div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83' }}>
                                <input type="checkbox" checked={!!previewReq.terminal} onChange={(e) => setPreviewReq({ ...previewReq, terminal: e.target.checked })} />
                                终端模式
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83' }}>
                                <input type="checkbox" checked={!!previewReq.timeout} onChange={(e) => setPreviewReq({ ...previewReq, timeout: e.target.checked })} />
                                超时
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83' }}>
                                <input type="checkbox" checked={!!previewReq.max_rounds_exhausted} onChange={(e) => setPreviewReq({ ...previewReq, max_rounds_exhausted: e.target.checked })} />
                                轮次耗尽
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#657b83' }}>
                                <input type="checkbox" checked={!!previewReq.auto_cancel} onChange={(e) => setPreviewReq({ ...previewReq, auto_cancel: e.target.checked })} />
                                自动撤单
                            </label>
                            <div style={{ gridColumn: '1 / span 2' }}>
                                <label style={{ display: 'block', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '4px' }}>最近状态统计（结构化数据）</label>
                                <textarea
                                    value={safeJson(previewReq.last_status_counts)}
                                    onChange={(e) => {
                                        try {
                                            const v = JSON.parse(e.target.value);
                                            setPreviewReq({ ...previewReq, last_status_counts: v });
                                        } catch {
                                            setPreviewReq({ ...previewReq, last_status_counts: {} });
                                        }
                                    }}
                                    style={{ width: '100%', minHeight: '80px', padding: '6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)', fontFamily: 'monospace' }}
                                />
                            </div>
                        </div>

                        <div style={{ marginTop: '10px', display: 'flex', gap: '8px' }}>
                            <button className="btn btn-primary btn-sm" onClick={preview} disabled={loading}>预览</button>
                            <button className="btn btn-secondary btn-sm" onClick={previewBatch} disabled={loading}>批量预览</button>
                        </div>
                    </div>
                </div>

                <div className="card">
                    <div className="card-header"><span className="card-title">📤 输出</span></div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '360px', overflow: 'auto' }}>
                            {loading ? '加载中...' : (output || '暂无输出')}
                        </pre>
                    </div>
                </div>
            </div>

            <div style={{ marginBottom: '12px' }}>
                <div className="card">
                    <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                        <span className="card-title">🛰️ 订单更新流</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                            <select
                                value={orderFilter.status}
                                onChange={(e) => setOrderFilter((s) => ({ ...s, status: e.target.value }))}
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            >
                                <option value="all">全部状态</option>
                                <option value="pending">待处理</option>
                                <option value="filled">已成交</option>
                                <option value="cancelled">已取消</option>
                                <option value="rejected">已拒绝</option>
                                <option value="partial">部分成交</option>
                            </select>
                            <input
                                value={orderFilter.orderId}
                                onChange={(e) => setOrderFilter((s) => ({ ...s, orderId: e.target.value }))}
                                placeholder="筛选订单编号"
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            />
                            <select
                                value={orderKeep}
                                onChange={(e) => setOrderKeep(Number(e.target.value))}
                                style={{ padding: '4px 6px', fontSize: '10px', borderRadius: '4px', border: '1px solid rgba(0,0,0,0.1)' }}
                            >
                                <option value={50}>保留 50</option>
                                <option value={100}>保留 100</option>
                                <option value={200}>保留 200</option>
                                <option value={500}>保留 500</option>
                            </select>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                                <input
                                    type="checkbox"
                                    checked={orderFilter.paused}
                                    onChange={(e) => setOrderFilter((s) => ({ ...s, paused: e.target.checked }))}
                                />
                                暂停
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: 'var(--text-muted)' }}>
                                <input type="checkbox" checked={showOrderRaw} onChange={(e) => setShowOrderRaw(e.target.checked)} />
                                原始数据
                            </label>
                            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{filteredOrderUpdates.length} 条</span>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => setOrderUpdates([])}
                                disabled={orderUpdates.length === 0}
                            >
                                清空
                            </button>
                        </div>
                    </div>
                    <div className="card-body" style={{ padding: '12px' }}>
                        {filteredOrderUpdates.length > 0 && (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '9px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                                <span>最新: {lastOrderUpdateAt || '-'}</span>
                                {Object.keys(orderStatusCounts).map((key) => (
                                    <span key={key} style={{ padding: '2px 6px', borderRadius: '10px', background: 'rgba(0,0,0,0.04)' }}>
                                        {getStatusLabel(key)}: {orderStatusCounts[key]}
                                    </span>
                                ))}
                            </div>
                        )}
                        {filteredOrderUpdates.length === 0 && (
                            <div style={{ color: 'var(--text-muted)', fontSize: '10px' }}>暂无订单更新（需要订单管理执行/对账/撤单触发）</div>
                        )}
                        {filteredOrderUpdates.length > 0 && showOrderRaw && (
                            <pre style={{ fontSize: '10px', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px', maxHeight: '240px', overflow: 'auto' }}>
                                {safeJson(filteredOrderUpdates)}
                            </pre>
                        )}
                        {filteredOrderUpdates.length > 0 && !showOrderRaw && (
                            <div style={{ maxHeight: '240px', overflow: 'auto' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '120px 80px 1fr 100px 70px 1fr 1fr 1fr', gap: '8px', fontSize: '9px', fontWeight: 700, marginBottom: '6px' }}>
                                    <div>时间</div>
                                    <div>状态</div>
                                    <div>订单编号</div>
                                    <div>交易对</div>
                                    <div>方向</div>
                                    <div>计划编号</div>
                                    <div>成交数量</div>
                                    <div>成交均价</div>
                                    <div>手续费</div>
                                </div>
                                {filteredOrderUpdates.map((item, idx) => (
                                    <div
                                        key={`${item?.payload?.order_id || 'order'}-${idx}`}
                                        style={{
                                            display: 'grid',
                                            gridTemplateColumns: '120px 80px 1fr 100px 70px 1fr 1fr 1fr',
                                            gap: '8px',
                                            fontSize: '9px',
                                            padding: '6px 0',
                                            borderBottom: '1px solid rgba(0,0,0,0.05)',
                                        }}
                                    >
                                        <div style={{ color: 'var(--text-muted)' }}>{item.received_at}</div>
                                        <div>{getStatusLabel(item?.payload?.status) || '-'}</div>
                                        <div style={{ fontFamily: 'monospace' }}>{item?.payload?.order_id || '-'}</div>
                                        <div>{item?.payload?.symbol || '-'}</div>
                                        <div>{getSideLabel(item?.payload?.side) || '-'}</div>
                                        <div style={{ fontFamily: 'monospace' }}>{item?.payload?.plan_id || '-'}</div>
                                        <div>{item?.payload?.filled_quantity ?? '-'}</div>
                                        <div>{item?.payload?.average_price ?? '-'}</div>
                                        <div>{item?.payload?.fee ?? '-'}</div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default OmsConsole;
