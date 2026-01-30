"""
Redis 数据结构设计文档
用于 Inarbit HFT 系统的实时数据缓存

基于以下原则设计:
1. 多交易所支持
2. 低延迟读取
3. 支持发布/订阅模式
"""

# ============================================
# Key Naming Convention (键命名规范)
# ============================================
# 格式: {namespace}:{exchange}:{data_type}:{symbol}
# 示例: inarbit:binance:ticker:BTC/USDT

# ============================================
# 1. 实时行情数据 (Ticker)
# ============================================
# Key: ticker:{exchange}:{symbol}
# Type: Hash
# TTL: 5 seconds (自动过期，防止脏数据)
# 
# Example:
#   HSET ticker:binance:BTC/USDT bid 68000.50 ask 68001.00 last 68000.75 volume 12345.67 timestamp 1705123456789
#
# Fields:
#   - bid: 买一价
#   - ask: 卖一价
#   - last: 最新成交价
#   - volume: 24h成交量
#   - timestamp: 更新时间戳 (ms)

# ============================================
# 2. 深度数据 (OrderBook)
# ============================================
# Key: orderbook:{exchange}:{symbol}:bids / orderbook:{exchange}:{symbol}:asks
# Type: Sorted Set (按价格排序)
# TTL: 2 seconds
#
# Example:
#   ZADD orderbook:binance:BTC/USDT:bids 68000.00 "68000.00:1.5"  # score=price, member="price:amount"
#   ZADD orderbook:binance:BTC/USDT:asks 68001.00 "68001.00:2.3"
#
# 获取 Top 10 买单: ZREVRANGE orderbook:binance:BTC/USDT:bids 0 9

# ============================================
# 3. 资金费率 (Funding Rate) - 期现套利用
# ============================================
# Key: funding:{exchange}:{symbol}
# Type: Hash
# TTL: 8 hours (每 8 小时更新)
#
# Fields:
#   - rate: 当前费率
#   - next_time: 下次结算时间
#   - predicted_rate: 预测费率

# ============================================
# 4. 交易对市场信息 (Markets)
# ============================================
# Key: markets:{exchange}
# Type: Hash
# TTL: 1 hour
#
# Example:
#   HSET markets:binance BTC/USDT '{"base":"BTC","quote":"USDT","active":true,"precision":{"price":2,"amount":6}}'

# ============================================
# 5. 策略运行状态 (Strategy Status)
# ============================================
# Key: strategy:status:{strategy_id}
# Type: Hash
# TTL: None (持久化)
#
# Fields:
#   - is_running: bool
#   - last_signal: 最后信号
#   - last_trade: 最后交易
#   - error: 错误信息 (如有)

# ============================================
# 6. 套利机会缓存 (Arbitrage Opportunities)
# ============================================
# Key: opportunities:{strategy_type}
# Type: Sorted Set (按利润率排序)
# TTL: 10 seconds
#
# Example:
#   ZADD opportunities:triangular 0.0025 '{"path":"USDT->BTC->ETH->USDT","profit_rate":0.0025}'

# ============================================
# 7. Pub/Sub 频道 (Channels)
# ============================================
# 订阅模式用于实时推送
#
# channel: signal:{user_id}:{strategy_type} - 套利信号（按用户隔离）
# channel: order:{user_id}:{status} - 订单状态变更（按用户隔离）
# channel: log:{user_id}:{level} - 系统日志（按用户隔离）
# channel: alert:{user_id} - 风控警报（按用户隔离）

# ============================================
# Redis 配置建议
# ============================================
# maxmemory: 512mb
# maxmemory-policy: volatile-ttl (优先删除即将过期的 key)
# tcp-keepalive: 60
