// risk.rs - Rust 风险管理模块
use crate::strategy::Signal;
use async_trait::async_trait;
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct RiskManager {
    // 配置可以从 YAML 加载，这里使用占位结构
    #[allow(dead_code)]
    pub config: Arc<RiskConfig>,
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
        Self { config: Arc::new(config) }
    }

    pub async fn check(&self, _signal: &Signal) -> bool {
        // 简化示例：总是返回 true，实际实现应查询数据库/缓存
        // TODO: 实现总权益、回撤、敞口等检查逻辑
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
