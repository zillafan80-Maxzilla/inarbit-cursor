use serde::{Deserialize, Serialize};

use crate::exchange::ExchangeId;

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StrategyType {
    Triangular,
    CashCarry,
    Pair,
    Grid,
    Graph,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Signal {
    pub strategy_id: String,
    pub strategy_type: StrategyType,
    pub exchange: ExchangeId,
    pub profit_rate: f64,
    pub expected_profit: f64,
    pub confidence: f64,
    pub path: String,
    pub timestamp: i64,
}

impl Signal {
    pub fn new(
        strategy_id: impl Into<String>,
        strategy_type: StrategyType,
        exchange: ExchangeId,
        profit_rate: f64,
        expected_profit: f64,
        confidence: f64,
        path: impl Into<String>,
        timestamp: i64,
    ) -> Self {
        Self {
            strategy_id: strategy_id.into(),
            strategy_type,
            exchange,
            profit_rate,
            expected_profit,
            confidence,
            path: path.into(),
            timestamp,
        }
    }
}
