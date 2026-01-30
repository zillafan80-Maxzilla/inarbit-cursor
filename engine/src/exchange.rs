//! 多交易所 WebSocket 连接模块

use anyhow::Result;
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

/// 交易所 ID
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExchangeId {
    Binance,
    Okx,
    Bybit,
    Gate,
    Bitget,
    Mexc,
}

impl ExchangeId {
    /// 获取 WebSocket URL
    pub fn ws_url(&self) -> &'static str {
        match self {
            ExchangeId::Binance => "wss://stream.binance.com:9443/ws",
            ExchangeId::Okx => "wss://ws.okx.com:8443/ws/v5/public",
            ExchangeId::Bybit => "wss://stream.bybit.com/v5/public/spot",
            ExchangeId::Gate => "wss://api.gateio.ws/ws/v4/",
            ExchangeId::Bitget => "wss://ws.bitget.com/spot/v1/stream",
            ExchangeId::Mexc => "wss://wbs.mexc.com/ws",
        }
    }
}

/// Ticker 数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Ticker {
    pub exchange: ExchangeId,
    pub symbol: String,
    pub bid: f64,
    pub ask: f64,
    pub last: f64,
    pub volume: f64,
    pub timestamp: i64,
}

/// 交易所连接
pub struct ExchangeConnection {
    pub id: ExchangeId,
    pub ticker_tx: broadcast::Sender<Ticker>,
    active: Arc<RwLock<bool>>,
}

impl ExchangeConnection {
    /// 创建新连接
    pub async fn new(id: ExchangeId) -> Result<Self> {
        let (ticker_tx, _) = broadcast::channel(1000);
        
        Ok(Self {
            id,
            ticker_tx,
            active: Arc::new(RwLock::new(false)),
        })
    }

    /// 订阅 Ticker
    pub fn subscribe_tickers(&self) -> broadcast::Receiver<Ticker> {
        self.ticker_tx.subscribe()
    }

    /// 启动 WebSocket 连接
    pub async fn start(&self, symbols: Vec<String>) -> Result<()> {
        let url = self.id.ws_url();
        info!("正在连接 {:?}: {}", self.id, url);

        let (ws_stream, _) = connect_async(url).await?;
        let (mut write, mut read) = ws_stream.split();

        // 设置为活跃
        *self.active.write().await = true;

        // 发送订阅消息
        let subscribe_msg = self.build_subscribe_message(&symbols);
        write.send(Message::Text(subscribe_msg)).await?;
        info!("{:?} 已订阅 {} 个交易对", self.id, symbols.len());

        // 读取消息
        let ticker_tx = self.ticker_tx.clone();
        let exchange_id = self.id;
        let active = self.active.clone();

        tokio::spawn(async move {
            while *active.read().await {
                match read.next().await {
                    Some(Ok(Message::Text(text))) => {
                        if let Some(ticker) = Self::parse_ticker(exchange_id, &text) {
                            let _ = ticker_tx.send(ticker);
                        }
                    }
                    Some(Ok(Message::Ping(_data))) => {
                        // 自动处理 ping/pong（忽略 ping payload，避免未使用告警）
                        info!("{:?} 收到 Ping", exchange_id);
                    }
                    Some(Err(e)) => {
                        error!("{:?} WebSocket 错误: {}", exchange_id, e);
                        break;
                    }
                    None => break,
                    _ => {}
                }
            }
            warn!("{:?} WebSocket 连接已断开", exchange_id);
        });

        Ok(())
    }

    /// 构建订阅消息 (不同交易所格式不同)
    fn build_subscribe_message(&self, symbols: &[String]) -> String {
        match self.id {
            ExchangeId::Binance => {
                // Binance 格式: {"method":"SUBSCRIBE","params":["btcusdt@ticker"],"id":1}
                let streams: Vec<String> = symbols
                    .iter()
                    .map(|s| format!("{}@ticker", s.to_lowercase().replace("/", "")))
                    .collect();
                serde_json::json!({
                    "method": "SUBSCRIBE",
                    "params": streams,
                    "id": 1
                }).to_string()
            }
            ExchangeId::Okx => {
                // OKX 格式
                let args: Vec<serde_json::Value> = symbols
                    .iter()
                    .map(|s| serde_json::json!({"channel": "tickers", "instId": s.replace("/", "-")}))
                    .collect();
                serde_json::json!({
                    "op": "subscribe",
                    "args": args
                }).to_string()
            }
            ExchangeId::Bybit => {
                // Bybit 格式
                let topics: Vec<String> = symbols
                    .iter()
                    .map(|s| format!("tickers.{}", s.replace("/", "")))
                    .collect();
                serde_json::json!({
                    "op": "subscribe",
                    "args": topics
                }).to_string()
            }
            _ => {
                // 默认格式
                serde_json::json!({
                    "type": "subscribe",
                    "channels": symbols
                }).to_string()
            }
        }
    }

    /// 解析 Ticker 消息 (不同交易所格式不同)
    fn parse_ticker(exchange: ExchangeId, msg: &str) -> Option<Ticker> {
        let json: serde_json::Value = serde_json::from_str(msg).ok()?;
        
        match exchange {
            ExchangeId::Binance => {
                // Binance ticker 格式
                if json.get("e")?.as_str()? != "24hrTicker" {
                    return None;
                }
                Some(Ticker {
                    exchange,
                    symbol: json.get("s")?.as_str()?.to_string(),
                    bid: json.get("b")?.as_str()?.parse().ok()?,
                    ask: json.get("a")?.as_str()?.parse().ok()?,
                    last: json.get("c")?.as_str()?.parse().ok()?,
                    volume: json.get("v")?.as_str()?.parse().ok()?,
                    timestamp: json.get("E")?.as_i64()?,
                })
            }
            ExchangeId::Okx => {
                let data = json.get("data")?.as_array()?.first()?;
                Some(Ticker {
                    exchange,
                    symbol: data.get("instId")?.as_str()?.to_string(),
                    bid: data.get("bidPx")?.as_str()?.parse().ok()?,
                    ask: data.get("askPx")?.as_str()?.parse().ok()?,
                    last: data.get("last")?.as_str()?.parse().ok()?,
                    volume: data.get("vol24h")?.as_str()?.parse().ok()?,
                    timestamp: data.get("ts")?.as_str()?.parse().ok()?,
                })
            }
            _ => None,
        }
    }

    /// 停止连接
    pub async fn stop(&self) {
        *self.active.write().await = false;
    }
}

/// 交易所配置
#[derive(Debug, Clone, Deserialize)]
pub struct ExchangeConfig {
    pub id: ExchangeId,
    pub api_key: String,
    pub api_secret: String,
    pub passphrase: Option<String>,
    pub enabled: bool,
}

/// 连接所有启用的交易所
pub async fn connect_all(configs: &[ExchangeConfig]) -> Result<HashMap<ExchangeId, Arc<ExchangeConnection>>> {
    let mut connections = HashMap::new();

    for config in configs.iter().filter(|c| c.enabled) {
        match ExchangeConnection::new(config.id).await {
            Ok(conn) => {
                info!("创建 {:?} 连接成功", config.id);
                connections.insert(config.id, Arc::new(conn));
            }
            Err(e) => {
                error!("创建 {:?} 连接失败: {}", config.id, e);
            }
        }
    }

    Ok(connections)
}
