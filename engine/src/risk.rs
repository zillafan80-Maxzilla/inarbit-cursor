// risk.rs - Rust 风险管理模块
use crate::strategy::Signal;
use async_trait::async_trait;
use reqwest::Client;
use std::sync::Arc;
use tracing::warn;

#[derive(Debug, Clone)]
pub struct RiskManager {
    // 配置可以从 YAML 加载，这里使用占位结构
    #[allow(dead_code)]
    pub config: Arc<RiskConfig>,
    remote: Option<RiskRemote>,
}

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
pub struct RiskConfig {
    pub max_drawdown: f64, // 如 0.2 表示 20%
    pub exposure_limit: f64,
    // 其他阈值
}

impl RiskManager {
    pub fn new(config: RiskConfig) -> Self {
        Self {
            config: Arc::new(config),
            remote: RiskRemote::from_env(),
        }
    }

    pub async fn check(&self, _signal: &Signal) -> bool {
        if let Some(remote) = &self.remote {
            match remote.check().await {
                Ok(allowed) => return allowed,
                Err(err) => warn!("remote risk check failed: {}", err),
            }
        }
        true
    }
}

// 为了在 engine 中统一调用，提供一个全局单例（示例）
lazy_static::lazy_static! {
    pub static ref GLOBAL_RISK_MANAGER: RiskManager = RiskManager::new(RiskConfig::default());
}

#[async_trait]
pub trait RiskCheck {
    async fn evaluate_risk(&self, signal: &Signal) -> bool;
}

#[async_trait]
impl RiskCheck for RiskManager {
    async fn evaluate_risk(&self, signal: &Signal) -> bool {
        self.check(signal).await
    }
}

#[derive(Debug, Clone)]
struct RiskRemote {
    base_url: String,
    token: String,
    http: Client,
}

impl RiskRemote {
    fn from_env() -> Option<Self> {
        let base = std::env::var("ENGINE_RISK_BASE").ok()
            .or_else(|| std::env::var("ENGINE_OMS_BASE").ok())?;
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

    async fn check(&self) -> anyhow::Result<bool> {
        let resp = self
            .http
            .get(format!("{}/api/v1/risk/status", self.base_url))
            .bearer_auth(&self.token)
            .send()
            .await?;
        let payload: serde_json::Value = resp.json().await?;
        Ok(payload
            .get("trading_allowed")
            .and_then(|v| v.as_bool())
            .unwrap_or(true))
    }
}
