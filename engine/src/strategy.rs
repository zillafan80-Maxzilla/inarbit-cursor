//! 策略引擎框架
//! 
//! 支持多策略注册、调度和融合

use anyhow::Result;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use tracing::{error, info, warn};
use uuid::Uuid;

use crate::exchange::{ExchangeConnection, ExchangeId, Ticker};
use crate::executor::OrderExecutor;
use crate::risk::{GLOBAL_RISK_MANAGER, RiskCheck};

/// 策略类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, sqlx::Type)]
#[sqlx(type_name = "strategy_type", rename_all = "lowercase")]
pub enum StrategyType {
    Triangular,   // 三角套利
    Graph,        // 图搜索套利
    FundingRate,  // 期现套利
    Grid,         // 网格交易
    Pair,         // 配对交易
}

/// 交易信号
#[derive(Debug, Clone, Serialize)]
pub struct Signal {
    pub strategy_type: StrategyType,
    pub strategy_id: Uuid,
    pub exchange: ExchangeId,
    pub path: String,
    pub expected_profit: f64,
    pub profit_rate: f64,
    pub confidence: f64,
    pub timestamp: i64,
}

/// 策略配置 (从数据库加载)
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct StrategyConfig {
    pub id: Uuid,
    #[sqlx(rename = "strategy_type")]
    pub strategy_type: StrategyType,
    pub name: String,
    pub is_enabled: bool,
    pub priority: i32,
    pub capital_percent: f64,
    pub per_trade_limit: f64,
    pub config: serde_json::Value,
}

/// 策略特征 (Trait)
#[async_trait]
#[allow(dead_code)]
pub trait Strategy: Send + Sync {
    /// 获取策略类型
    fn strategy_type(&self) -> StrategyType;
    
    /// 获取策略 ID
    fn strategy_id(&self) -> Uuid;
    
    /// 处理 Ticker 更新
    async fn on_ticker(&mut self, ticker: &Ticker) -> Option<Signal>;
    
    /// 策略初始化
    async fn initialize(&mut self) -> Result<()>;
    
    /// 策略停止
    async fn shutdown(&mut self);
}

/// 策略引擎
pub struct Engine {
    db_pool: PgPool,
    redis: redis::Client,
    strategies: Arc<RwLock<Vec<Box<dyn Strategy>>>>,
    running: Arc<RwLock<bool>>,
}

impl Engine {
    /// 创建新引擎
    pub fn new(db_pool: PgPool, redis: redis::Client) -> Self {
        Self {
            db_pool,
            redis,
            strategies: Arc::new(RwLock::new(Vec::new())),
            running: Arc::new(RwLock::new(false)),
        }
    }

    /// 从数据库加载启用的策略（无配置时加载默认策略）
    pub async fn load_enabled_strategies(
        &mut self,
        exchanges: &HashMap<ExchangeId, Arc<ExchangeConnection>>,
    ) -> Result<()> {
        let configs: Vec<StrategyConfig> = sqlx::query_as(
            r#"
            SELECT id, strategy_type, name, is_enabled, priority,
                   capital_percent::float8 as capital_percent,
                   per_trade_limit::float8 as per_trade_limit,
                   config
            FROM strategy_configs
            WHERE is_enabled = true
            ORDER BY priority ASC
            "#
        )
        .fetch_all(&self.db_pool)
        .await?;

        let mut strategies = self.strategies.write().await;

        if configs.is_empty() {
            if let Some(exchange_id) = choose_default_exchange(exchanges) {
                let bases = self.get_top_base_symbols(exchange_id, 3).await;
                let fallback_bases = vec!["BTC".to_string(), "ETH".to_string(), "BNB".to_string()];
                let selected_bases = if bases.is_empty() { fallback_bases } else { bases };
                let triangles = build_triangles(exchange_id, &selected_bases);

                let triangle_payload: Vec<Vec<String>> = triangles
                    .iter()
                    .map(|(a, b, c)| vec![a.clone(), b.clone(), c.clone()])
                    .collect();

                let default_config = StrategyConfig {
                    id: Uuid::new_v4(),
                    strategy_type: StrategyType::Triangular,
                    name: "default-triangular".to_string(),
                    is_enabled: true,
                    priority: 1,
                    capital_percent: 20.0,
                    per_trade_limit: 100.0,
                    config: serde_json::json!({
                        "triangles": triangle_payload,
                        "bases": selected_bases,
                        "exchange_id": format!("{:?}", exchange_id).to_lowercase(),
                        "default": true,
                        "regime_weights": {
                            "RANGE": 1.0,
                            "DOWNTREND": 0.6,
                            "UPTREND": 0.7,
                            "STRESS": 0.2
                        },
                        "allow_short": false,
                        "max_leverage": 1.0
                    }),
                };

                match self.create_strategy(default_config.clone()) {
                    Ok(strategy) => {
                        info!(
                            "未启用任何策略，已加载默认三角策略（exchange={}, bases={:?}）",
                            format!("{:?}", exchange_id).to_lowercase(),
                            default_config.config.get("bases")
                        );
                        strategies.push(strategy);
                    }
                    Err(e) => {
                        error!("创建默认策略失败: {}", e);
                    }
                }
            } else {
                warn!("未发现可用交易所连接，无法加载默认策略");
            }
            return Ok(());
        }

        for config in configs {
            match self.create_strategy(config.clone()) {
                Ok(strategy) => {
                    info!("加载策略: {} ({:?})", config.name, config.strategy_type);
                    strategies.push(strategy);
                }
                Err(e) => {
                    error!("创建策略失败 {}: {}", config.name, e);
                }
            }
        }

        Ok(())
    }

    async fn get_top_base_symbols(&self, exchange_id: ExchangeId, limit: usize) -> Vec<String> {
        let exchange_key = format!("{:?}", exchange_id).to_lowercase();
        let index_key = format!("symbols:ticker:{}", exchange_key);

        let mut conn = match self.redis.get_multiplexed_async_connection().await {
            Ok(conn) => conn,
            Err(e) => {
                warn!("读取 Redis 失败，无法获取交易量排行: {}", e);
                return Vec::new();
            }
        };

        let symbols: Vec<String> = match redis::AsyncCommands::smembers(&mut conn, &index_key).await {
            Ok(list) => list,
            Err(_) => return Vec::new(),
        };

        if symbols.is_empty() {
            return Vec::new();
        }

        let mut pipe = redis::pipe();
        for symbol in &symbols {
            let key = format!("ticker:{}:{}", exchange_key, symbol);
            pipe.cmd("HGET").arg(key).arg("volume");
        }

        let volumes: Vec<Option<String>> = pipe.query_async(&mut conn).await.unwrap_or_default();
        let mut ranked: Vec<(String, f64)> = Vec::new();
        for (symbol, volume_raw) in symbols.into_iter().zip(volumes.into_iter()) {
            if !symbol.ends_with("/USDT") && !symbol.ends_with("-USDT") && !symbol.ends_with("USDT") {
                continue;
            }
            let volume = volume_raw
                .and_then(|v| v.parse::<f64>().ok())
                .unwrap_or(0.0);
            ranked.push((symbol, volume));
        }

        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let mut out = Vec::new();
        let mut seen = HashSet::new();
        for (symbol, _) in ranked {
            let base = if let Some((base, _)) = symbol.split_once('/') {
                base.to_string()
            } else if let Some((base, _)) = symbol.split_once('-') {
                base.to_string()
            } else if symbol.ends_with("USDT") {
                symbol.trim_end_matches("USDT").to_string()
            } else {
                continue;
            };

            if base.is_empty() || !seen.insert(base.clone()) {
                continue;
            }
            out.push(base);
            if out.len() >= limit {
                break;
            }
        }

        out
    }

    /// 根据配置创建策略实例
    fn create_strategy(&self, config: StrategyConfig) -> Result<Box<dyn Strategy>> {
        match config.strategy_type {
            StrategyType::Triangular => {
                Ok(Box::new(TriangularStrategy::new(config)))
            }
            StrategyType::Graph => {
                Ok(Box::new(GraphStrategy::new(config)))
            }
            StrategyType::FundingRate => {
                Ok(Box::new(FundingRateStrategy::new(config)))
            }
            StrategyType::Grid => {
                Ok(Box::new(GridStrategy::new(config)))
            }
            StrategyType::Pair => {
                Ok(Box::new(PairStrategy::new(config)))
            }
        }
    }

    /// 获取策略数量
    pub fn strategy_count(&self) -> usize {
        // 使用 try_read 避免阻塞
        self.strategies.try_read().map(|s| s.len()).unwrap_or(0)
    }

    /// 运行引擎
    pub async fn run(
        &self,
        exchanges: HashMap<ExchangeId, Arc<ExchangeConnection>>,
        executor: &OrderExecutor,
    ) -> Result<()> {
        *self.running.write().await = true;
        info!("策略引擎开始运行");

        let execute_signals = std::env::var("ENGINE_EXECUTE_SIGNALS")
            .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
            .unwrap_or(false);

        if exchanges.is_empty() {
            anyhow::bail!("没有可用的交易所连接");
        }

        // 合并多个交易所的 Ticker 流
        let (ticker_tx, mut ticker_rx) = mpsc::channel::<Ticker>(1000);
        for (exchange_id, conn) in exchanges.iter() {
            let mut rx = conn.subscribe_tickers();
            let tx = ticker_tx.clone();
            let exchange_id = *exchange_id;

            tokio::spawn(async move {
                loop {
                    match rx.recv().await {
                        Ok(ticker) => {
                            if tx.send(ticker).await.is_err() {
                                break;
                            }
                        }
                        Err(tokio::sync::broadcast::error::RecvError::Lagged(count)) => {
                            warn!("{:?} ticker 丢失 {} 条", exchange_id, count);
                        }
                        Err(tokio::sync::broadcast::error::RecvError::Closed) => {
                            break;
                        }
                    }
                }
                warn!("{:?} ticker 流已关闭", exchange_id);
            });
        }

        while *self.running.read().await {
            tokio::select! {
                Some(ticker) = ticker_rx.recv() => {
                    // 分发 Ticker 到所有策略
                    let mut strategies = self.strategies.write().await;
                    for strategy in strategies.iter_mut() {
                        if let Some(signal) = strategy.on_ticker(&ticker).await {
                            // 发现信号，发送到执行器
                            info!("信号: {:?} -> {:.4}%", signal.strategy_type, signal.profit_rate * 100.0);

                            if !GLOBAL_RISK_MANAGER.evaluate_risk(&signal).await {
                                warn!("信号被风控拦截: {:?}", signal.strategy_type);
                                self.record_blocked_metric(signal.strategy_type).await;
                                continue;
                            }

                            if execute_signals {
                                if let Err(e) = executor.execute(signal.clone()).await {
                                    error!("执行器错误: {}", e);
                                }
                            }

                            // 推送到 Redis（保留监控/联调）
                            self.publish_signal(&signal).await;
                            self.record_signal_metric(&signal).await;
                        }
                    }
                }
            }
        }

        Ok(())
    }

    /// 发布信号到 Redis
    async fn publish_signal(&self, signal: &Signal) {
        // 使用多路复用连接，兼容新版 redis 客户端
        if let Ok(mut conn) = self.redis.get_multiplexed_async_connection().await {
            let channel = match std::env::var("ENGINE_USER_ID") {
                Ok(user_id) if !user_id.is_empty() => {
                    format!("signal:{}:{:?}", user_id, signal.strategy_type).to_lowercase()
                }
                _ => format!("signal:{:?}", signal.strategy_type).to_lowercase(),
            };
            let payload = serde_json::to_string(signal).unwrap_or_default();
            let _: Result<(), _> = redis::cmd("PUBLISH")
                .arg(&channel)
                .arg(&payload)
                .query_async(&mut conn)
                .await;
        }
    }

    async fn record_signal_metric(&self, signal: &Signal) {
        if let Ok(mut conn) = self.redis.get_multiplexed_async_connection().await {
            use redis::AsyncCommands;
            let strategy_key = format!(
                "metrics:engine:strategy:{}",
                format!("{:?}", signal.strategy_type).to_lowercase()
            );
            let _: Result<(), _> = conn.hset(
                "metrics:engine",
                "last_signal_ts",
                signal.timestamp.to_string(),
            ).await;
            let _: Result<(), _> = conn.hset(
                "metrics:engine",
                "last_strategy_type",
                format!("{:?}", signal.strategy_type).to_lowercase(),
            ).await;
            let _: Result<(), _> = conn.incr("metrics:engine:signal_count", 1_i64).await;
            let _: Result<(), _> = conn.incr(format!("{}:signal_count", strategy_key), 1_i64).await;
            let _: Result<(), _> = conn.hset(
                &strategy_key,
                "last_signal_ts",
                signal.timestamp.to_string(),
            ).await;
        }
    }

    async fn record_blocked_metric(&self, strategy_type: StrategyType) {
        if let Ok(mut conn) = self.redis.get_multiplexed_async_connection().await {
            use redis::AsyncCommands;
            let strategy_key = format!(
                "metrics:engine:strategy:{}",
                format!("{:?}", strategy_type).to_lowercase()
            );
            let _: Result<(), _> = conn.hset(
                "metrics:engine",
                "last_blocked_strategy_type",
                format!("{:?}", strategy_type).to_lowercase(),
            ).await;
            let _: Result<(), _> = conn.incr("metrics:engine:blocked_count", 1_i64).await;
            let _: Result<(), _> = conn.incr(format!("{}:blocked_count", strategy_key), 1_i64).await;
            let _: Result<(), _> = conn.hset(
                &strategy_key,
                "last_blocked_ts",
                chrono::Utc::now().timestamp_millis().to_string(),
            ).await;
        }
    }

    /// 关闭引擎
    pub async fn shutdown(&self) {
        *self.running.write().await = false;
        
        let mut strategies = self.strategies.write().await;
        for strategy in strategies.iter_mut() {
            strategy.shutdown().await;
        }
        
        info!("策略引擎已关闭");
    }
}

fn choose_default_exchange(
    exchanges: &HashMap<ExchangeId, Arc<ExchangeConnection>>,
) -> Option<ExchangeId> {
    if exchanges.contains_key(&ExchangeId::Binance) {
        return Some(ExchangeId::Binance);
    }
    if exchanges.contains_key(&ExchangeId::Okx) {
        return Some(ExchangeId::Okx);
    }
    exchanges.keys().next().copied()
}

fn build_triangles(exchange_id: ExchangeId, bases: &[String]) -> Vec<(String, String, String)> {
    let sep = match exchange_id {
        ExchangeId::Okx => "-",
        _ => "",
    };

    let mut out = Vec::new();
    for a in bases {
        for b in bases {
            if a == b {
                continue;
            }
            let pair1 = format!("{}{}USDT", a, sep);
            let pair2 = format!("{}{}{}", b, sep, a);
            let pair3 = format!("{}{}USDT", b, sep);
            out.push((pair1, pair2, pair3));
        }
    }
    out
}

// ============================================
// 策略实现
// ============================================

/// 三角套利策略
/// 
/// 检测 A→B→C→A 形式的套利机会
/// 例如: USDT→BTC→ETH→USDT
pub struct TriangularStrategy {
    config: StrategyConfig,
    // 价格缓存: symbol -> (bid, ask, timestamp)
    prices: HashMap<String, (f64, f64, i64)>,
    // 预定义的三角路径
    triangles: Vec<(String, String, String)>,
    // 最小利润率阈值
    min_profit_rate: f64,
    // 手续费率 (每笔交易)
    fee_rate: f64,
}

impl TriangularStrategy {
    pub fn new(config: StrategyConfig) -> Self {
        // 从配置中读取参数
        let min_profit_rate = config.config.get("min_profit_rate")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.001); // 默认 0.1%
        let fee_rate = config.config.get("fee_rate")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.001); // 默认 0.1%
        
        // 预定义常见的三角路径（可被配置覆盖）
        let fallback_triangles = vec![
            ("BTCUSDT".to_string(), "ETHBTC".to_string(), "ETHUSDT".to_string()),
            ("BTCUSDT".to_string(), "BNBBTC".to_string(), "BNBUSDT".to_string()),
            ("ETHUSDT".to_string(), "BNBETH".to_string(), "BNBUSDT".to_string()),
            ("BTCUSDT".to_string(), "SOLBTC".to_string(), "SOLUSDT".to_string()),
            ("BTCUSDT".to_string(), "XRPBTC".to_string(), "XRPUSDT".to_string()),
        ];

        let triangles = config
            .config
            .get("triangles")
            .and_then(|v| v.as_array())
            .map(|items| {
                let mut out = Vec::new();
                for item in items {
                    if let Some(arr) = item.as_array() {
                        if arr.len() == 3 {
                            if let (Some(a), Some(b), Some(c)) =
                                (arr[0].as_str(), arr[1].as_str(), arr[2].as_str())
                            {
                                out.push((a.to_string(), b.to_string(), c.to_string()));
                            }
                        }
                    }
                }
                out
            })
            .filter(|out| !out.is_empty())
            .unwrap_or(fallback_triangles);
        
        Self { 
            config,
            prices: HashMap::new(),
            triangles,
            min_profit_rate,
            fee_rate,
        }
    }
    
    /// 计算三角套利利润
    /// 路径: 用 quote 买入 base1，用 base1 买入 base2，卖出 base2 换回 quote
    fn calculate_profit(&self, pair1: &str, pair2: &str, pair3: &str) -> Option<(f64, f64)> {
        let (_, ask1, _) = self.prices.get(pair1)?; // 买入价
        let (_, ask2, _) = self.prices.get(pair2)?; // 买入价
        let (bid3, _, _) = self.prices.get(pair3)?; // 卖出价
        
        // 假设初始资金为 1
        // 第一步: 1 USDT → 1/ask1 BTC
        let step1 = 1.0 / ask1 * (1.0 - self.fee_rate);
        // 第二步: step1 BTC → step1/ask2 ETH
        let step2 = step1 / ask2 * (1.0 - self.fee_rate);
        // 第三步: step2 ETH → step2 * bid3 USDT
        let final_amount = step2 * bid3 * (1.0 - self.fee_rate);
        
        // 利润率
        let profit_rate = final_amount - 1.0;
        
        Some((profit_rate, final_amount))
    }
}

#[async_trait]
impl Strategy for TriangularStrategy {
    fn strategy_type(&self) -> StrategyType {
        StrategyType::Triangular
    }
    
    fn strategy_id(&self) -> Uuid {
        self.config.id
    }
    
    async fn on_ticker(&mut self, ticker: &Ticker) -> Option<Signal> {
        // 更新价格缓存
        self.prices.insert(
            ticker.symbol.clone(),
            (ticker.bid, ticker.ask, ticker.timestamp)
        );
        
        // 检查所有三角路径
        for (pair1, pair2, pair3) in &self.triangles {
            if let Some((profit_rate, _)) = self.calculate_profit(pair1, pair2, pair3) {
                if profit_rate > self.min_profit_rate {
                    return Some(Signal {
                        strategy_type: StrategyType::Triangular,
                        strategy_id: self.config.id,
                        exchange: ticker.exchange,
                        path: format!("{} → {} → {}", pair1, pair2, pair3),
                        expected_profit: profit_rate * self.config.per_trade_limit,
                        profit_rate,
                        confidence: (profit_rate / self.min_profit_rate).min(1.0),
                        timestamp: chrono::Utc::now().timestamp_millis(),
                    });
                }
            }
        }
        
        None
    }
    
    async fn initialize(&mut self) -> Result<()> {
        info!("三角套利策略初始化完成，监控 {} 条路径", self.triangles.len());
        Ok(())
    }
    
    async fn shutdown(&mut self) {
        self.prices.clear();
    }
}

/// 图搜索套利策略
/// 
/// 使用 Bellman-Ford 算法检测负权环（套利机会）
pub struct GraphStrategy {
    config: StrategyConfig,
    // 价格图: (from, to) -> log_price
    edges: HashMap<(String, String), f64>,
    // 所有币种节点
    nodes: Vec<String>,
    // 最小利润率
    min_profit_rate: f64,
    // 手续费率
    fee_rate: f64,
}

impl GraphStrategy {
    pub fn new(config: StrategyConfig) -> Self {
        let min_profit_rate = config.config.get("min_profit_rate")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.002);
        let fee_rate = config.config.get("fee_rate")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.001);
            
        Self { 
            config,
            edges: HashMap::new(),
            nodes: vec!["USDT".to_string(), "BTC".to_string(), "ETH".to_string(), 
                       "BNB".to_string(), "SOL".to_string(), "XRP".to_string()],
            min_profit_rate,
            fee_rate,
        }
    }
    
    /// 使用 Bellman-Ford 检测负权环
    fn detect_negative_cycle(&self) -> Option<(Vec<String>, f64)> {
        let n = self.nodes.len();
        if n == 0 { return None; }
        
        // 距离数组
        let mut dist: HashMap<&str, f64> = HashMap::new();
        let mut parent: HashMap<&str, &str> = HashMap::new();
        
        for node in &self.nodes {
            dist.insert(node, f64::INFINITY);
        }
        dist.insert(&self.nodes[0], 0.0);
        
        // 松弛 n-1 次
        for _ in 0..n {
            for ((from, to), weight) in &self.edges {
                // 先获取 from 的距离值
                let d_from = match dist.get(from.as_str()) {
                    Some(&d) => d,
                    None => continue,
                };
                // 再获取并更新 to 的距离值
                if let Some(d_to) = dist.get_mut(to.as_str()) {
                    if d_from + weight < *d_to {
                        *d_to = d_from + weight;
                        parent.insert(to.as_str(), from.as_str());
                    }
                }
            }
        }
        
        // 检测负权环
        for ((from, to), weight) in &self.edges {
            if let (Some(&d_from), Some(&d_to)) = (dist.get(from.as_str()), dist.get(to.as_str())) {
                if d_from + weight < d_to {
                    // 发现负权环，构建路径
                    let mut path = vec![to.clone()];
                    let mut current = from.as_str();
                    while !path.contains(&current.to_string()) && path.len() < n + 1 {
                        path.push(current.to_string());
                        current = parent.get(current).unwrap_or(&"");
                    }
                    path.reverse();
                    
                    // 计算利润率
                    let profit = (-weight).exp() - 1.0;
                    return Some((path, profit));
                }
            }
        }
        
        None
    }
}

#[async_trait]
impl Strategy for GraphStrategy {
    fn strategy_type(&self) -> StrategyType {
        StrategyType::Graph
    }
    
    fn strategy_id(&self) -> Uuid {
        self.config.id
    }
    
    async fn on_ticker(&mut self, ticker: &Ticker) -> Option<Signal> {
        // 解析交易对，更新边权重
        // 边权重 = -log(price * (1 - fee))
        let symbol = &ticker.symbol;
        if let Some(base_quote) = Self::parse_pair(symbol) {
            let (base, quote) = base_quote;
            // 买入边: quote -> base
            let buy_weight = -(ticker.ask * (1.0 - self.fee_rate)).ln();
            self.edges.insert((quote.clone(), base.clone()), buy_weight);
            // 卖出边: base -> quote
            let sell_weight = (ticker.bid * (1.0 - self.fee_rate)).ln();
            self.edges.insert((base, quote), sell_weight);
        }
        
        // 检测套利机会
        if let Some((path, profit_rate)) = self.detect_negative_cycle() {
            if profit_rate > self.min_profit_rate {
                return Some(Signal {
                    strategy_type: StrategyType::Graph,
                    strategy_id: self.config.id,
                    exchange: ticker.exchange,
                    path: path.join(" → "),
                    expected_profit: profit_rate * self.config.per_trade_limit,
                    profit_rate,
                    confidence: (profit_rate / self.min_profit_rate).min(1.0),
                    timestamp: chrono::Utc::now().timestamp_millis(),
                });
            }
        }
        
        None
    }
    
    async fn initialize(&mut self) -> Result<()> {
        info!("图搜索策略初始化完成，监控 {} 个节点", self.nodes.len());
        Ok(())
    }
    
    async fn shutdown(&mut self) {
        self.edges.clear();
    }
}

impl GraphStrategy {
    fn parse_pair(symbol: &str) -> Option<(String, String)> {
        // 简单解析: BTCUSDT -> (BTC, USDT)
        for quote in ["USDT", "USDC", "BTC", "ETH", "BNB"] {
            if symbol.ends_with(quote) {
                let base = symbol.strip_suffix(quote)?;
                return Some((base.to_string(), quote.to_string()));
            }
        }
        None
    }
}

/// 期现套利策略
/// 
/// 利用永续合约资金费率进行套利
/// 正资金费率时：做空永续 + 买入现货
/// 负资金费率时：做多永续 + 卖出现货
pub struct FundingRateStrategy {
    config: StrategyConfig,
    // 资金费率缓存: symbol -> (rate, next_funding_time)
    funding_rates: HashMap<String, (f64, i64)>,
    // 现货价格缓存
    spot_prices: HashMap<String, f64>,
    // 永续合约价格缓存
    perp_prices: HashMap<String, f64>,
    // 最小年化收益率阈值
    min_apr: f64,
    // 持仓天数
    holding_days: f64,
}

impl FundingRateStrategy {
    pub fn new(config: StrategyConfig) -> Self {
        let min_apr = config.config.get("min_apr")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.10); // 默认 10% 年化
        let holding_days = config.config.get("holding_days")
            .and_then(|v| v.as_f64())
            .unwrap_or(7.0);
            
        Self {
            config,
            funding_rates: HashMap::new(),
            spot_prices: HashMap::new(),
            perp_prices: HashMap::new(),
            min_apr,
            holding_days,
        }
    }
    
    /// 计算预期年化收益
    fn calculate_apr(&self, symbol: &str) -> Option<f64> {
        let (funding_rate, _) = self.funding_rates.get(symbol)?;
        // 资金费率每 8 小时结算一次，一天 3 次
        // 年化 = 日收益率 * 365
        let daily_rate = funding_rate.abs() * 3.0;
        let apr = daily_rate * 365.0;
        Some(apr)
    }
}

#[async_trait]
impl Strategy for FundingRateStrategy {
    fn strategy_type(&self) -> StrategyType {
        StrategyType::FundingRate
    }
    
    fn strategy_id(&self) -> Uuid {
        self.config.id
    }
    
    async fn on_ticker(&mut self, ticker: &Ticker) -> Option<Signal> {
        let symbol = &ticker.symbol;
        
        // 更新价格（简化处理，实际需区分现货/永续）
        self.spot_prices.insert(symbol.clone(), ticker.last);
        
        // 模拟资金费率（实际应从 API 获取）
        // 这里假设已经通过其他渠道获取了资金费率
        if let Some(apr) = self.calculate_apr(symbol) {
            if apr > self.min_apr {
                let (funding_rate, _) = self.funding_rates.get(symbol)?;
                let direction = if *funding_rate > 0.0 { "做空永续+买入现货" } else { "做多永续+卖出现货" };
                
                return Some(Signal {
                    strategy_type: StrategyType::FundingRate,
                    strategy_id: self.config.id,
                    exchange: ticker.exchange,
                    path: format!("{} - {}", symbol, direction),
                    expected_profit: apr * self.holding_days / 365.0 * self.config.per_trade_limit,
                    profit_rate: apr,
                    confidence: (apr / self.min_apr).min(1.0),
                    timestamp: chrono::Utc::now().timestamp_millis(),
                });
            }
        }
        
        None
    }
    
    async fn initialize(&mut self) -> Result<()> {
        info!("期现套利策略初始化完成，最小年化阈值 {:.1}%", self.min_apr * 100.0);
        Ok(())
    }
    
    async fn shutdown(&mut self) {
        self.funding_rates.clear();
        self.spot_prices.clear();
        self.perp_prices.clear();
    }
}

impl FundingRateStrategy {
    /// 更新资金费率（由外部调用）
    #[allow(dead_code)]
    pub fn update_funding_rate(&mut self, symbol: &str, rate: f64, next_time: i64) {
        self.funding_rates.insert(symbol.to_string(), (rate, next_time));
    }
}

/// 网格交易策略
/// 
/// 在价格区间内布置网格，低买高卖
pub struct GridStrategy {
    config: StrategyConfig,
    // 网格配置: symbol -> GridConfig
    grids: HashMap<String, GridConfig>,
    // 当前持仓
    positions: HashMap<String, f64>,
}

#[derive(Clone)]
#[allow(dead_code)]
struct GridConfig {
    upper_price: f64,      // 网格上限
    lower_price: f64,      // 网格下限
    grid_count: usize,     // 网格数量
    grid_size: f64,        // 每格间距
    last_trigger: f64,     // 上次触发价格
}

impl GridStrategy {
    pub fn new(config: StrategyConfig) -> Self {
        let mut grids = HashMap::new();
        
        // 从配置读取网格参数
        if let Some(grid_configs) = config.config.get("grids").and_then(|v| v.as_array()) {
            for gc in grid_configs {
                if let (Some(symbol), Some(upper), Some(lower), Some(count)) = (
                    gc.get("symbol").and_then(|v| v.as_str()),
                    gc.get("upper_price").and_then(|v| v.as_f64()),
                    gc.get("lower_price").and_then(|v| v.as_f64()),
                    gc.get("grid_count").and_then(|v| v.as_u64()),
                ) {
                    let grid_size = (upper - lower) / count as f64;
                    grids.insert(symbol.to_string(), GridConfig {
                        upper_price: upper,
                        lower_price: lower,
                        grid_count: count as usize,
                        grid_size,
                        last_trigger: (upper + lower) / 2.0,
                    });
                }
            }
        }
        
        Self {
            config,
            grids,
            positions: HashMap::new(),
        }
    }
}

#[async_trait]
impl Strategy for GridStrategy {
    fn strategy_type(&self) -> StrategyType {
        StrategyType::Grid
    }
    
    fn strategy_id(&self) -> Uuid {
        self.config.id
    }
    
    async fn on_ticker(&mut self, ticker: &Ticker) -> Option<Signal> {
        let symbol = &ticker.symbol;
        let price = ticker.last;
        
        let grid = self.grids.get_mut(symbol)?;
        
        // 检查是否在网格范围内
        if price < grid.lower_price || price > grid.upper_price {
            return None;
        }
        
        // 计算当前网格层级
        let current_grid = ((price - grid.lower_price) / grid.grid_size).floor();
        let last_grid = ((grid.last_trigger - grid.lower_price) / grid.grid_size).floor();
        
        // 检查是否跨越网格线
        if (current_grid - last_grid).abs() >= 1.0 {
            let direction = if price < grid.last_trigger { "买入" } else { "卖出" };
            let profit_rate = grid.grid_size / price; // 单格利润率
            
            grid.last_trigger = price;
            
            return Some(Signal {
                strategy_type: StrategyType::Grid,
                strategy_id: self.config.id,
                exchange: ticker.exchange,
                path: format!("{} - {} @ {:.2}", symbol, direction, price),
                expected_profit: profit_rate * self.config.per_trade_limit,
                profit_rate,
                confidence: 0.8, // 网格策略置信度较稳定
                timestamp: chrono::Utc::now().timestamp_millis(),
            });
        }
        
        None
    }
    
    async fn initialize(&mut self) -> Result<()> {
        info!("网格交易策略初始化完成，监控 {} 个交易对", self.grids.len());
        Ok(())
    }
    
    async fn shutdown(&mut self) {
        self.positions.clear();
    }
}

/// 配对交易策略
/// 
/// 基于 Z-Score 均值回归的配对交易
/// 当价差偏离均值时开仓，回归时平仓
pub struct PairStrategy {
    config: StrategyConfig,
    // 配对关系: (symbol1, symbol2)
    pairs: Vec<(String, String)>,
    // 价格历史 (用于计算均值和标准差)
    price_history: HashMap<String, Vec<f64>>,
    // 历史窗口大小
    window_size: usize,
    // Z-Score 阈值
    zscore_threshold: f64,
}

impl PairStrategy {
    pub fn new(config: StrategyConfig) -> Self {
        // 预定义相关性较高的配对
        let pairs = vec![
            ("BTCUSDT".to_string(), "ETHUSDT".to_string()),
            ("SOLUSDT".to_string(), "AVAXUSDT".to_string()),
            ("BNBUSDT".to_string(), "MATICUSDT".to_string()),
        ];
        
        let window_size = config.config.get("window_size")
            .and_then(|v| v.as_u64())
            .unwrap_or(100) as usize;
        let zscore_threshold = config.config.get("zscore_threshold")
            .and_then(|v| v.as_f64())
            .unwrap_or(2.0);
            
        Self {
            config,
            pairs,
            price_history: HashMap::new(),
            window_size,
            zscore_threshold,
        }
    }
    
    /// 计算 Z-Score
    fn calculate_zscore(&self, sym1: &str, sym2: &str) -> Option<f64> {
        let hist1 = self.price_history.get(sym1)?;
        let hist2 = self.price_history.get(sym2)?;
        
        if hist1.len() < self.window_size || hist2.len() < self.window_size {
            return None;
        }
        
        // 计算价格比率的历史数据
        let ratios: Vec<f64> = hist1.iter().zip(hist2.iter())
            .map(|(p1, p2)| p1 / p2)
            .collect();
        
        // 计算均值和标准差
        let mean = ratios.iter().sum::<f64>() / ratios.len() as f64;
        let variance = ratios.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / ratios.len() as f64;
        let std_dev = variance.sqrt();
        
        if std_dev == 0.0 {
            return None;
        }
        
        // 当前比率的 Z-Score
        let current_ratio = hist1.last()? / hist2.last()?;
        let zscore = (current_ratio - mean) / std_dev;
        
        Some(zscore)
    }
}

#[async_trait]
impl Strategy for PairStrategy {
    fn strategy_type(&self) -> StrategyType {
        StrategyType::Pair
    }
    
    fn strategy_id(&self) -> Uuid {
        self.config.id
    }
    
    async fn on_ticker(&mut self, ticker: &Ticker) -> Option<Signal> {
        let symbol = &ticker.symbol;
        
        // 更新价格历史
        let history = self.price_history.entry(symbol.clone()).or_insert_with(Vec::new);
        history.push(ticker.last);
        if history.len() > self.window_size {
            history.remove(0);
        }
        
        // 检查所有配对
        for (sym1, sym2) in &self.pairs {
            if symbol == sym1 || symbol == sym2 {
                if let Some(zscore) = self.calculate_zscore(sym1, sym2) {
                    if zscore.abs() > self.zscore_threshold {
                        let direction = if zscore > 0.0 {
                            format!("做空 {} / 做多 {}", sym1, sym2)
                        } else {
                            format!("做多 {} / 做空 {}", sym1, sym2)
                        };
                        
                        // 预期利润：Z-Score 回归到 0 时的收益
                        let profit_rate = (zscore.abs() - self.zscore_threshold) * 0.01;
                        
                        return Some(Signal {
                            strategy_type: StrategyType::Pair,
                            strategy_id: self.config.id,
                            exchange: ticker.exchange,
                            path: format!("{}/{} - {}", sym1, sym2, direction),
                            expected_profit: profit_rate * self.config.per_trade_limit,
                            profit_rate,
                            confidence: (zscore.abs() / (self.zscore_threshold * 2.0)).min(1.0),
                            timestamp: chrono::Utc::now().timestamp_millis(),
                        });
                    }
                }
            }
        }
        
        None
    }
    
    async fn initialize(&mut self) -> Result<()> {
        info!("配对交易策略初始化完成，监控 {} 个配对", self.pairs.len());
        Ok(())
    }
    
    async fn shutdown(&mut self) {
        self.price_history.clear();
    }
}
