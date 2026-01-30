//! 订单执行引擎

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{error, info};

use crate::exchange::{ExchangeConnection, ExchangeId};
use crate::strategy::Signal;
use redis::AsyncCommands;
use reqwest::Client;

/// 订单方向
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum OrderSide {
    Buy,
    Sell,
}

/// 订单类型
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[allow(dead_code)]
pub enum OrderType {
    Market,
    Limit,
}

/// 订单请求
#[derive(Debug, Clone, Serialize)]
#[allow(dead_code)]
pub struct OrderRequest {
    pub exchange: ExchangeId,
    pub symbol: String,
    pub side: OrderSide,
    pub order_type: OrderType,
    pub amount: f64,
    pub price: Option<f64>,
}

/// 订单响应
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderResponse {
    pub order_id: String,
    pub exchange: ExchangeId,
    pub symbol: String,
    pub side: OrderSide,
    pub status: OrderStatus,
    pub filled_amount: f64,
    pub avg_price: f64,
    pub fee: f64,
    pub latency_ms: u64,
}

/// 订单状态
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum OrderStatus {
    Pending,
    PartialFilled,
    Filled,
    Cancelled,
    Failed,
}

/// 执行结果
#[derive(Debug, Clone, Serialize)]
pub struct ExecutionResult {
    pub signal: Signal,
    pub orders: Vec<OrderResponse>,
    pub total_fee: f64,
    pub net_profit: f64,
    pub success: bool,
}

/// 订单执行器
pub struct OrderExecutor {
    #[allow(dead_code)]
    exchanges: HashMap<ExchangeId, Arc<ExchangeConnection>>,
    // 可选: 模拟模式
    simulation_mode: bool,
    redis: Option<redis::Client>,
    oms_client: Option<OmsClient>,
    user_id: Option<String>,
}

impl OrderExecutor {
    /// 创建新执行器
    pub fn new(
        exchanges: HashMap<ExchangeId, Arc<ExchangeConnection>>,
        redis: Option<redis::Client>,
    ) -> Self {
        Self {
            exchanges,
            simulation_mode: true, // 默认模拟模式
            redis,
            oms_client: OmsClient::from_env(),
            user_id: std::env::var("ENGINE_USER_ID").ok().filter(|v| !v.is_empty()),
        }
    }

    /// 设置模拟模式
    pub fn set_simulation_mode(&mut self, enabled: bool) {
        self.simulation_mode = enabled;
    }

    /// 执行套利信号
    pub async fn execute(&self, signal: Signal) -> Result<ExecutionResult> {
        info!(
            "执行信号: {:?} @ {:?}, 预期收益: {:.4}%",
            signal.strategy_type, signal.exchange, signal.profit_rate * 100.0
        );

        if self.simulation_mode {
            return self.simulate_execution(signal).await;
        }

        if !self.live_enabled() {
            return Err(anyhow::anyhow!(
                "live execution blocked: require ENGINE_EXECUTE_SIGNALS=1 and ENGINE_LIVE_CONFIRM=CONFIRM_LIVE"
            ));
        }

        let decision_payload = self.build_decision_payload(&signal);
        self.publish_signal(&signal, &decision_payload).await;
        self.publish_decision(&decision_payload).await?;

        if let Some(client) = &self.oms_client {
            let idempotency_key = format!("engine:{}:{}", signal.strategy_id, signal.timestamp);
            let success = client
                .execute_latest(idempotency_key, self.simulation_mode)
                .await?;
            return Ok(ExecutionResult {
                signal,
                orders: vec![],
                total_fee: 0.0,
                net_profit: 0.0,
                success,
            });
        }

        Err(anyhow::anyhow!("OMS client not configured (ENGINE_OMS_BASE/ENGINE_OMS_TOKEN)"))
    }

    /// 模拟执行
    async fn simulate_execution(&self, signal: Signal) -> Result<ExecutionResult> {
        let simulated_order = OrderResponse {
            order_id: uuid::Uuid::new_v4().to_string(),
            exchange: signal.exchange,
            symbol: "SIMULATED".to_string(),
            side: OrderSide::Buy,
            status: OrderStatus::Filled,
            filled_amount: 100.0,
            avg_price: 1.0,
            fee: 0.1,
            latency_ms: 50,
        };

        let result = ExecutionResult {
            signal: signal.clone(),
            orders: vec![simulated_order],
            total_fee: 0.1,
            net_profit: signal.expected_profit - 0.1,
            success: true,
        };

        info!("模拟执行完成: 净收益 ${:.4}", result.net_profit);
        
        Ok(result)
    }

    /// 执行市价单
    #[allow(dead_code)]
    pub async fn market_order(
        &self,
        exchange: ExchangeId,
        symbol: &str,
        side: OrderSide,
        amount: f64,
    ) -> Result<OrderResponse> {
        let request = OrderRequest {
            exchange,
            symbol: symbol.to_string(),
            side,
            order_type: OrderType::Market,
            amount,
            price: None,
        };

        self.send_order(request).await
    }

    /// 执行限价单
    #[allow(dead_code)]
    pub async fn limit_order(
        &self,
        exchange: ExchangeId,
        symbol: &str,
        side: OrderSide,
        amount: f64,
        price: f64,
    ) -> Result<OrderResponse> {
        let request = OrderRequest {
            exchange,
            symbol: symbol.to_string(),
            side,
            order_type: OrderType::Limit,
            amount,
            price: Some(price),
        };

        self.send_order(request).await
    }

    /// 发送订单到交易所
    #[allow(dead_code)]
    async fn send_order(&self, request: OrderRequest) -> Result<OrderResponse> {
        let _conn = self.exchanges.get(&request.exchange)
            .ok_or_else(|| anyhow::anyhow!("交易所 {:?} 未连接", request.exchange))?;

        // TODO: 实现真实的订单发送
        // 1. 使用交易所 REST API 发送订单
        // 2. 等待订单确认
        // 3. 返回执行结果

        if self.simulation_mode {
            return Ok(OrderResponse {
                order_id: uuid::Uuid::new_v4().to_string(),
                exchange: request.exchange,
                symbol: request.symbol,
                side: request.side,
                status: OrderStatus::Filled,
                filled_amount: request.amount,
                avg_price: request.price.unwrap_or(1.0),
                fee: request.amount * 0.001,
                latency_ms: 30,
            });
        }

        if !self.live_enabled() {
            return Err(anyhow::anyhow!(
                "live execution blocked: require ENGINE_EXECUTE_SIGNALS=1 and ENGINE_LIVE_CONFIRM=CONFIRM_LIVE"
            ));
        }

        Err(anyhow::anyhow!("订单发送未实现"))
    }

    fn build_decision_payload(&self, signal: &Signal) -> serde_json::Value {
        let symbols = parse_symbols_from_path(&signal.path);
        let symbol = symbols.first().cloned().unwrap_or_default();
        serde_json::json!({
            "strategyType": format!("{:?}", signal.strategy_type).to_lowercase(),
            "exchange": format!("{:?}", signal.exchange).to_lowercase(),
            "symbol": symbol,
            "direction": "neutral",
            "expectedProfit": signal.expected_profit,
            "expectedProfitRate": signal.profit_rate,
            "estimatedExposure": 0.0,
            "riskScore": calc_risk_score(signal.profit_rate),
            "confidence": signal.confidence,
            "timestamp": signal.timestamp,
            "rawOpportunity": {
                "path": signal.path,
                "symbols": symbols,
            }
        })
    }

    async fn publish_signal(&self, signal: &Signal, payload: &serde_json::Value) {
        let Some(redis) = &self.redis else {
            return;
        };
        let Some(user_id) = &self.user_id else {
            return;
        };
        if let Ok(mut conn) = redis.get_multiplexed_async_connection().await {
            let channel = format!(
                "signal:{}:{}",
                user_id,
                format!("{:?}", signal.strategy_type).to_lowercase()
            );
            let _ = conn.publish::<_, _, ()>(channel, payload.to_string()).await;
        }
    }

    async fn publish_decision(&self, payload: &serde_json::Value) -> Result<()> {
        let Some(redis) = &self.redis else {
            return Ok(());
        };
        let risk_score = payload
            .get("riskScore")
            .and_then(|v| v.as_f64())
            .unwrap_or(1.0);
        let mut conn = redis.get_multiplexed_async_connection().await?;
        let _: () = conn
            .zadd("decisions:latest", payload.to_string(), risk_score)
            .await?;
        let _: () = conn.expire("decisions:latest", 10).await?;
        Ok(())
    }

    fn live_enabled(&self) -> bool {
        let execute_signals = std::env::var("ENGINE_EXECUTE_SIGNALS")
            .map(|v| matches!(v.as_str(), "1" | "true" | "True"))
            .unwrap_or(false);
        let live_confirm = std::env::var("ENGINE_LIVE_CONFIRM").unwrap_or_default();
        execute_signals && live_confirm == "CONFIRM_LIVE"
    }

    /// 批量执行订单 (原子性套利)
    #[allow(dead_code)]
    pub async fn execute_batch(&self, orders: Vec<OrderRequest>) -> Result<Vec<OrderResponse>> {
        // 并发执行所有订单
        let mut handles = vec![];
        
        for order in orders {
            let executor = self.clone_for_task();
            handles.push(tokio::spawn(async move {
                executor.send_order(order).await
            }));
        }

        let mut results = vec![];
        for handle in handles {
            match handle.await {
                Ok(Ok(response)) => results.push(response),
                Ok(Err(e)) => error!("订单执行失败: {}", e),
                Err(e) => error!("任务错误: {}", e),
            }
        }

        Ok(results)
    }

    /// 为异步任务克隆自身
    #[allow(dead_code)]
    fn clone_for_task(&self) -> Self {
        Self {
            exchanges: self.exchanges.clone(),
            simulation_mode: self.simulation_mode,
            redis: self.redis.clone(),
            oms_client: self.oms_client.clone(),
            user_id: self.user_id.clone(),
        }
    }
}

#[derive(Clone)]
struct OmsClient {
    base_url: String,
    token: String,
    http: Client,
}

impl OmsClient {
    fn from_env() -> Option<Self> {
        let base = std::env::var("ENGINE_OMS_BASE").ok()?;
        let token = std::env::var("ENGINE_OMS_TOKEN").ok()?;
        if base.is_empty() || token.is_empty() {
            return None;
        }
        Some(Self {
            base_url: base.trim_end_matches('/').to_string(),
            token,
            http: Client::new(),
        })
    }

    async fn execute_latest(&self, idempotency_key: String, simulation_mode: bool) -> Result<bool> {
        let trading_mode = if simulation_mode { "paper" } else { "live" };
        let resp = self
            .http
            .post(format!("{}/api/v1/oms/execute_latest", self.base_url))
            .bearer_auth(&self.token)
            .json(&serde_json::json!({
                "trading_mode": trading_mode,
                "confirm_live": !simulation_mode,
                "idempotency_key": idempotency_key,
                "limit": 1
            }))
            .send()
            .await?;
        let payload: serde_json::Value = resp.json().await?;
        if !payload.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
            return Err(anyhow::anyhow!("OMS execute_latest failed: {:?}", payload));
        }
        Ok(true)
    }
}

fn parse_symbols_from_path(path: &str) -> Vec<String> {
    if path.is_empty() {
        return vec![];
    }
    let mut out = vec![];
    for part in path.split("->") {
        let symbol = part.trim().trim_matches(',');
        if !symbol.is_empty() {
            out.push(symbol.to_string());
        }
    }
    if out.is_empty() {
        out.push(path.to_string());
    }
    out
}

fn calc_risk_score(profit_rate: f64) -> f64 {
    let base = (1.0 - profit_rate).max(0.01);
    (base * 1000.0).min(1000.0)
}
