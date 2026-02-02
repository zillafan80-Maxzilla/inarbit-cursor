import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const fetchAPI = async (path) => {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('auth_token') || ''}`,
      'Content-Type': 'application/json'
    }
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
};

export default function RuntimeStats() {
  const [stats, setStats] = useState(null);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  // 每3秒刷新统计数据
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetchAPI('/api/v1/stats/realtime');
        if (res.success) {
          setStats(res.data);
        }
      } catch (error) {
        console.error('获取统计数据失败:', error);
      } finally {
        setLoading(false);
      }
    };

    const fetchTrades = async () => {
      try {
        const res = await fetchAPI('/api/v1/stats/trades/recent?limit=20');
        if (res.success) {
          setTrades(res.data);
        }
      } catch (error) {
        console.error('获取交易记录失败:', error);
      }
    };

    fetchStats();
    fetchTrades();
    
    const statsInterval = setInterval(fetchStats, 3000);
    const tradesInterval = setInterval(fetchTrades, 5000);

    return () => {
      clearInterval(statsInterval);
      clearInterval(tradesInterval);
    };
  }, []);

  if (loading) {
    return <div className="p-6">加载中...</div>;
  }

  if (!stats || !stats.runtime) {
    return <div className="p-6">暂无统计数据</div>;
  }

  // 安全的数据访问，提供默认值
  const runtime = stats.runtime || { hours: 0, minutes: 0, seconds: 0 };
  const tradingMode = stats.trading_mode || '未知';
  const initialBalance = stats.initial_balance || 0;
  const currentBalance = stats.current_balance || 0;
  const netProfit = stats.net_profit || 0;
  const activeStrategies = (stats.active_strategies || ['无']).filter(s => s && s !== '无');
  const activeExchanges = (stats.active_exchanges || ['无']).filter(e => e && e !== '无');
  const tradingPairs = (stats.trading_pairs || ['无']).filter(p => p && p !== '无');

  // 格式化收益曲线数据
  const chartData = (stats.profit_history || []).map(item => ({
    time: new Date(item.timestamp * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    balance: item.balance,
    profit: item.balance - initialBalance
  }));

  return (
    <div className="p-6 space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">实时运行统计</h1>
        <div className="text-sm text-gray-500">
          最后更新: {new Date(stats.current_time).toLocaleString('zh-CN')}
        </div>
      </div>

      {/* 核心统计信息卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 运行时长 */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-semibold mb-1">运行时长</div>
          <div className="text-2xl font-bold text-blue-900">
            {runtime.hours}小时 {runtime.minutes}分 {runtime.seconds}秒
          </div>
        </div>

        {/* 运行模式 */}
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
          <div className="text-sm text-purple-600 font-semibold mb-1">运行模式</div>
          <div className="text-2xl font-bold text-purple-900">
            {tradingMode === 'paper' ? '模拟盘' : tradingMode === 'live' ? '实盘' : '未知'}
          </div>
        </div>

        {/* 初始资金 */}
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="text-sm text-green-600 font-semibold mb-1">初始资金</div>
          <div className="text-2xl font-bold text-green-900">
            ${initialBalance.toFixed(2)}
          </div>
        </div>

        {/* 当前资金 */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="text-sm text-yellow-600 font-semibold mb-1">当前资金</div>
          <div className="text-2xl font-bold text-yellow-900">
            ${currentBalance.toFixed(2)}
          </div>
        </div>

        {/* 净利润 */}
        <div className={`border rounded-lg p-4 ${netProfit >= 0 ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
          <div className={`text-sm font-semibold mb-1 ${netProfit >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>净利润</div>
          <div className={`text-2xl font-bold ${netProfit >= 0 ? 'text-emerald-900' : 'text-red-900'}`}>
            {netProfit >= 0 ? '+' : ''}{netProfit.toFixed(2)} USDT
          </div>
          <div className={`text-xs mt-1 ${netProfit >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            收益率: {initialBalance > 0 ? ((netProfit / initialBalance) * 100).toFixed(2) : 0}%
          </div>
        </div>

        {/* 活跃策略 */}
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4">
          <div className="text-sm text-indigo-600 font-semibold mb-1">交易策略</div>
          <div className="text-sm text-indigo-900 space-y-1">
            {activeStrategies.length > 0 ? (
              activeStrategies.map((s, i) => <div key={i}>• {s}</div>)
            ) : (
              <div className="text-gray-500">无</div>
            )}
          </div>
        </div>

        {/* 连接的交易所 */}
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
          <div className="text-sm text-orange-600 font-semibold mb-1">交易所</div>
          <div className="text-sm text-orange-900 space-y-1">
            {activeExchanges.length > 0 ? (
              activeExchanges.map((e, i) => <div key={i}>• {e.toUpperCase()}</div>)
            ) : (
              <div className="text-gray-500">无</div>
            )}
          </div>
        </div>

        {/* 交易币对 */}
        <div className="bg-pink-50 border border-pink-200 rounded-lg p-4">
          <div className="text-sm text-pink-600 font-semibold mb-1">交易币对</div>
          <div className="text-xs text-pink-900 max-h-16 overflow-y-auto">
            {tradingPairs.length > 0 ? (
              tradingPairs.map((p, i) => <span key={i} className="inline-block mr-2">{p}</span>)
            ) : (
              <div className="text-gray-500">无</div>
            )}
          </div>
        </div>
      </div>

      {/* 收益曲线图 */}
      <div className="bg-white border rounded-lg p-6">
        <h2 className="text-xl font-bold mb-4">实时收益曲线</h2>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="balance" stroke="#8884d8" name="总资金 (USDT)" />
              <Line type="monotone" dataKey="profit" stroke="#82ca9d" name="利润 (USDT)" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-center text-gray-500 py-12">暂无收益数据</div>
        )}
      </div>

      {/* 实时交易记录 */}
      <div className="bg-white border rounded-lg p-6">
        <h2 className="text-xl font-bold mb-4">实时交易记录</h2>
        {trades && trades.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left">时间</th>
                  <th className="px-4 py-2 text-left">类型</th>
                  <th className="px-4 py-2 text-left">币对</th>
                  <th className="px-4 py-2 text-left">方向</th>
                  <th className="px-4 py-2 text-right">价格</th>
                  <th className="px-4 py-2 text-right">数量</th>
                  <th className="px-4 py-2 text-right">收益</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {trades.map((trade, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-2">{new Date(trade.timestamp).toLocaleString('zh-CN')}</td>
                    <td className="px-4 py-2">
                      <span className={`px-2 py-1 rounded text-xs ${trade.type === 'buy' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {trade.type === 'buy' ? '买入' : '卖出'}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono">{trade.symbol}</td>
                    <td className="px-4 py-2">{trade.side}</td>
                    <td className="px-4 py-2 text-right font-mono">${trade.price?.toFixed(4) || '0.0000'}</td>
                    <td className="px-4 py-2 text-right font-mono">{trade.amount?.toFixed(6) || '0.000000'}</td>
                    <td className={`px-4 py-2 text-right font-mono font-semibold ${trade.profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {trade.profit >= 0 ? '+' : ''}{trade.profit?.toFixed(2) || '0.00'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center text-gray-500 py-12">暂无交易记录</div>
        )}
      </div>
    </div>
  );
}
