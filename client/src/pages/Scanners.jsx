import React, { useEffect, useMemo, useState } from 'react';
import { scannerAPI } from '../api/client';

function toNumberOrUndefined(v) {
  if (v === null || v === undefined) return undefined;
  const s = String(v).trim();
  if (s === '') return undefined;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
}

function toIntOrUndefined(v) {
  const n = toNumberOrUndefined(v);
  if (n === undefined) return undefined;
  return Number.isFinite(n) ? parseInt(String(n), 10) : undefined;
}

const Scanners = () => {
  const [raw, setRaw] = useState(null);
  const [tri, setTri] = useState({
    exchange_id: '',
    base_currency: '',
    min_profit_rate: '',
    fee_rate: '',
    refresh_interval_seconds: '',
    ttl_seconds: '',
    max_opportunities: '',
  });
  const [cc, setCc] = useState({
    exchange_id: '',
    quote_currency: '',
    min_profit_rate: '',
    spot_fee_rate: '',
    perp_fee_rate: '',
    funding_horizon_intervals: '',
    refresh_interval_seconds: '',
    ttl_seconds: '',
    max_opportunities: '',
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({ triangular: false, cashcarry: false });
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await scannerAPI.status();
      setRaw(resp || null);
      const t = resp?.triangular || {};
      const c = resp?.cashcarry || {};
      setTri({
        exchange_id: t.exchange_id ?? '',
        base_currency: t.base_currency ?? '',
        min_profit_rate: t.min_profit_rate ?? '',
        fee_rate: t.fee_rate ?? '',
        refresh_interval_seconds: t.refresh_interval_seconds ?? '',
        ttl_seconds: t.ttl_seconds ?? '',
        max_opportunities: t.max_opportunities ?? '',
      });
      setCc({
        exchange_id: c.exchange_id ?? '',
        quote_currency: c.quote_currency ?? '',
        min_profit_rate: c.min_profit_rate ?? '',
        spot_fee_rate: c.spot_fee_rate ?? '',
        perp_fee_rate: c.perp_fee_rate ?? '',
        funding_horizon_intervals: c.funding_horizon_intervals ?? '',
        refresh_interval_seconds: c.refresh_interval_seconds ?? '',
        ttl_seconds: c.ttl_seconds ?? '',
        max_opportunities: c.max_opportunities ?? '',
      });
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const triMetrics = raw?.triangular?.metrics || null;
  const ccMetrics = raw?.cashcarry?.metrics || null;

  const saveTri = async () => {
    setSaving((p) => ({ ...p, triangular: true }));
    try {
      await scannerAPI.updateTriangular({
        exchange_id: tri.exchange_id || undefined,
        base_currency: tri.base_currency || undefined,
        min_profit_rate: toNumberOrUndefined(tri.min_profit_rate),
        fee_rate: toNumberOrUndefined(tri.fee_rate),
        refresh_interval_seconds: toNumberOrUndefined(tri.refresh_interval_seconds),
        ttl_seconds: toIntOrUndefined(tri.ttl_seconds),
        max_opportunities: toIntOrUndefined(tri.max_opportunities),
      });
      await load();
      alert('Triangular 扫描器参数已更新');
    } catch (e) {
      alert(String(e?.message || e));
    }
    setSaving((p) => ({ ...p, triangular: false }));
  };

  const saveCc = async () => {
    setSaving((p) => ({ ...p, cashcarry: true }));
    try {
      await scannerAPI.updateCashCarry({
        exchange_id: cc.exchange_id || undefined,
        quote_currency: cc.quote_currency || undefined,
        min_profit_rate: toNumberOrUndefined(cc.min_profit_rate),
        spot_fee_rate: toNumberOrUndefined(cc.spot_fee_rate),
        perp_fee_rate: toNumberOrUndefined(cc.perp_fee_rate),
        funding_horizon_intervals: toIntOrUndefined(cc.funding_horizon_intervals),
        refresh_interval_seconds: toNumberOrUndefined(cc.refresh_interval_seconds),
        ttl_seconds: toIntOrUndefined(cc.ttl_seconds),
        max_opportunities: toIntOrUndefined(cc.max_opportunities),
      });
      await load();
      alert('CashCarry 扫描器参数已更新');
    } catch (e) {
      alert(String(e?.message || e));
    }
    setSaving((p) => ({ ...p, cashcarry: false }));
  };

  const healthHint = useMemo(() => {
    if (!triMetrics && !ccMetrics) return null;
    const triMs = Number(triMetrics?.last_scan_ms || 0);
    const ccMs = Number(ccMetrics?.last_scan_ms || 0);
    const slow = Math.max(triMs, ccMs);
    if (slow >= 5000) return { level: 'danger', text: '扫描延迟较高，可能需要降低 symbols/提高 interval' };
    if (slow >= 1000) return { level: 'warning', text: '扫描延迟偏高，建议观察 CPU/行情 loop' };
    return { level: 'success', text: '扫描延迟正常' };
  }, [triMetrics, ccMetrics]);

  return (
    <div className="content-body">
      <div className="page-header" style={{ marginBottom: '16px' }}>
        <div>
          <h1 className="page-title">扫描器参数</h1>
          <p className="page-subtitle">运行时动态调整 triangular / cashcarry 扫描器（管理员）</p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={load} className="btn btn-secondary">🔄 刷新</button>
        </div>
      </div>

      {loading && (
        <div className="loading">
          <div className="loading-spinner"></div>
        </div>
      )}

      {!loading && error && (
        <div className="stat-box" style={{ padding: '12px', color: 'var(--color-danger)' }}>
          {error}
          <div style={{ marginTop: '8px', fontSize: '10px', color: 'var(--text-muted)' }}>
            说明：该页面需要管理员权限；若出现 403/401，请确认已用管理员账号登录。
          </div>
        </div>
      )}

      {!loading && !error && (
        <>
          {healthHint && (
            <div
              className="stat-box"
              style={{
                padding: '10px 12px',
                marginBottom: '12px',
                background: healthHint.level === 'danger'
                  ? 'rgba(220, 50, 47, 0.08)'
                  : healthHint.level === 'warning'
                    ? 'rgba(181, 137, 0, 0.08)'
                    : 'rgba(133, 153, 0, 0.08)',
              }}
            >
              <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                {healthHint.text}
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div className="stat-box" style={{ padding: '12px' }}>
              <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>🔺 Triangular</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
                <div>
                  <label className="form-label">exchange_id</label>
                  <input className="form-input" value={tri.exchange_id} onChange={(e) => setTri((p) => ({ ...p, exchange_id: e.target.value }))} placeholder="okx / binance" />
                </div>
                <div>
                  <label className="form-label">base_currency</label>
                  <input className="form-input" value={tri.base_currency} onChange={(e) => setTri((p) => ({ ...p, base_currency: e.target.value }))} placeholder="USDT" />
                </div>
                <div>
                  <label className="form-label">min_profit_rate</label>
                  <input className="form-input" value={tri.min_profit_rate} onChange={(e) => setTri((p) => ({ ...p, min_profit_rate: e.target.value }))} placeholder="0.0015" />
                </div>
                <div>
                  <label className="form-label">fee_rate</label>
                  <input className="form-input" value={tri.fee_rate} onChange={(e) => setTri((p) => ({ ...p, fee_rate: e.target.value }))} placeholder="0.0004" />
                </div>
                <div>
                  <label className="form-label">refresh_interval_seconds</label>
                  <input className="form-input" value={tri.refresh_interval_seconds} onChange={(e) => setTri((p) => ({ ...p, refresh_interval_seconds: e.target.value }))} placeholder="2" />
                </div>
                <div>
                  <label className="form-label">ttl_seconds</label>
                  <input className="form-input" value={tri.ttl_seconds} onChange={(e) => setTri((p) => ({ ...p, ttl_seconds: e.target.value }))} placeholder="10" />
                </div>
                <div>
                  <label className="form-label">max_opportunities</label>
                  <input className="form-input" value={tri.max_opportunities} onChange={(e) => setTri((p) => ({ ...p, max_opportunities: e.target.value }))} placeholder="50" />
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end' }}>
                  <button className="btn btn-primary" onClick={saveTri} disabled={saving.triangular}>
                    {saving.triangular ? '保存中...' : '保存 Triangular'}
                  </button>
                </div>
              </div>

              <div style={{ marginTop: '10px', fontSize: '10px', color: 'var(--text-muted)' }}>
                {triMetrics ? (
                  <>
                    last_scan_ms={triMetrics.last_scan_ms} · pairs={triMetrics.pairs} · opportunities={triMetrics.opportunities} · ts={triMetrics.timestamp_ms}
                  </>
                ) : (
                  '暂无指标'
                )}
              </div>
            </div>

            <div className="stat-box" style={{ padding: '12px' }}>
              <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>💹 CashCarry</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
                <div>
                  <label className="form-label">exchange_id</label>
                  <input className="form-input" value={cc.exchange_id} onChange={(e) => setCc((p) => ({ ...p, exchange_id: e.target.value }))} placeholder="okx / binance" />
                </div>
                <div>
                  <label className="form-label">quote_currency</label>
                  <input className="form-input" value={cc.quote_currency} onChange={(e) => setCc((p) => ({ ...p, quote_currency: e.target.value }))} placeholder="USDT" />
                </div>
                <div>
                  <label className="form-label">min_profit_rate</label>
                  <input className="form-input" value={cc.min_profit_rate} onChange={(e) => setCc((p) => ({ ...p, min_profit_rate: e.target.value }))} placeholder="0.0010" />
                </div>
                <div>
                  <label className="form-label">spot_fee_rate</label>
                  <input className="form-input" value={cc.spot_fee_rate} onChange={(e) => setCc((p) => ({ ...p, spot_fee_rate: e.target.value }))} placeholder="0.0004" />
                </div>
                <div>
                  <label className="form-label">perp_fee_rate</label>
                  <input className="form-input" value={cc.perp_fee_rate} onChange={(e) => setCc((p) => ({ ...p, perp_fee_rate: e.target.value }))} placeholder="0.0004" />
                </div>
                <div>
                  <label className="form-label">funding_horizon_intervals</label>
                  <input className="form-input" value={cc.funding_horizon_intervals} onChange={(e) => setCc((p) => ({ ...p, funding_horizon_intervals: e.target.value }))} placeholder="3" />
                </div>
                <div>
                  <label className="form-label">refresh_interval_seconds</label>
                  <input className="form-input" value={cc.refresh_interval_seconds} onChange={(e) => setCc((p) => ({ ...p, refresh_interval_seconds: e.target.value }))} placeholder="2" />
                </div>
                <div>
                  <label className="form-label">ttl_seconds</label>
                  <input className="form-input" value={cc.ttl_seconds} onChange={(e) => setCc((p) => ({ ...p, ttl_seconds: e.target.value }))} placeholder="10" />
                </div>
                <div>
                  <label className="form-label">max_opportunities</label>
                  <input className="form-input" value={cc.max_opportunities} onChange={(e) => setCc((p) => ({ ...p, max_opportunities: e.target.value }))} placeholder="50" />
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end' }}>
                  <button className="btn btn-primary" onClick={saveCc} disabled={saving.cashcarry}>
                    {saving.cashcarry ? '保存中...' : '保存 CashCarry'}
                  </button>
                </div>
              </div>

              <div style={{ marginTop: '10px', fontSize: '10px', color: 'var(--text-muted)' }}>
                {ccMetrics ? (
                  <>
                    last_scan_ms={ccMetrics.last_scan_ms} · symbols={ccMetrics.symbols} · opportunities={ccMetrics.opportunities} · ts={ccMetrics.timestamp_ms}
                  </>
                ) : (
                  '暂无指标'
                )}
              </div>
            </div>
          </div>

          <div className="stat-box" style={{ padding: '12px', marginTop: '12px' }}>
            <h3 style={{ fontSize: '11px', marginBottom: '10px', fontWeight: 600 }}>原始返回</h3>
            <pre style={{ fontSize: '10px', whiteSpace: 'pre-wrap', maxHeight: '360px', overflow: 'auto', background: 'rgba(0,0,0,0.02)', padding: '10px', borderRadius: '6px' }}>
              {JSON.stringify(raw || {}, null, 2)}
            </pre>
          </div>
        </>
      )}
    </div>
  );
};

export default Scanners;

