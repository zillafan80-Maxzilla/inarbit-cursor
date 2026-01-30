//! 配置加载模块

use anyhow::Result;
use serde::Deserialize;
use std::env;

use crate::exchange::ExchangeConfig;

/// 应用配置
#[derive(Debug, Deserialize)]
pub struct AppConfig {
    pub mode: String,
    pub database: DatabaseConfig,
    pub redis: RedisConfig,
    pub exchanges: Vec<ExchangeConfig>,
}

/// 数据库配置
#[derive(Debug, Deserialize)]
pub struct DatabaseConfig {
    pub host: String,
    pub port: u16,
    pub user: String,
    pub password: String,
    pub database: String,
}

impl DatabaseConfig {
    /// 生成连接 URL
    pub fn url(&self) -> String {
        format!(
            "postgres://{}:{}@{}:{}/{}",
            self.user, self.password, self.host, self.port, self.database
        )
    }
}

/// Redis 配置
#[derive(Debug, Deserialize)]
pub struct RedisConfig {
    pub host: String,
    pub port: u16,
    pub password: Option<String>,
    pub db: u8,
}

impl RedisConfig {
    /// 生成连接 URL
    pub fn url(&self) -> String {
        match &self.password {
            Some(pwd) if !pwd.is_empty() => {
                format!("redis://:{}@{}:{}/{}", pwd, self.host, self.port, self.db)
            }
            _ => {
                format!("redis://{}:{}/{}", self.host, self.port, self.db)
            }
        }
    }
}

/// 加载配置
pub fn load_config() -> Result<AppConfig> {
    let config = AppConfig {
        mode: env::var("ENGINE_MODE").unwrap_or_else(|_| "simulation".to_string()),
        database: DatabaseConfig {
            host: env::var("POSTGRES_HOST").unwrap_or_else(|_| "localhost".to_string()),
            port: env::var("POSTGRES_PORT")
                .unwrap_or_else(|_| "5432".to_string())
                .parse()?,
            user: env::var("POSTGRES_USER").unwrap_or_else(|_| "inarbit".to_string()),
            // 默认密码与 docker-compose 保持一致，避免本地启动失败
            password: env::var("POSTGRES_PASSWORD").unwrap_or_else(|_| "inarbit_secret_2026".to_string()),
            database: env::var("POSTGRES_DB").unwrap_or_else(|_| "inarbit".to_string()),
        },
        redis: RedisConfig {
            host: env::var("REDIS_HOST").unwrap_or_else(|_| "localhost".to_string()),
            port: env::var("REDIS_PORT")
                .unwrap_or_else(|_| "6379".to_string())
                .parse()?,
            password: env::var("REDIS_PASSWORD").ok().filter(|s| !s.is_empty()),
            db: env::var("REDIS_DB")
                .unwrap_or_else(|_| "0".to_string())
                .parse()?,
        },
        exchanges: load_exchange_configs(),
    };

    Ok(config)
}

/// 加载交易所配置
fn load_exchange_configs() -> Vec<ExchangeConfig> {
    use crate::exchange::ExchangeId;
    
    let mut configs = vec![];

    // Binance
    if let Ok(key) = env::var("BINANCE_API_KEY") {
        if !key.is_empty() {
            configs.push(ExchangeConfig {
                id: ExchangeId::Binance,
                api_key: key,
                api_secret: env::var("BINANCE_API_SECRET").unwrap_or_default(),
                passphrase: None,
                enabled: true,
            });
        }
    }

    // OKX
    if let Ok(key) = env::var("OKX_API_KEY") {
        if !key.is_empty() {
            configs.push(ExchangeConfig {
                id: ExchangeId::Okx,
                api_key: key,
                api_secret: env::var("OKX_API_SECRET").unwrap_or_default(),
                passphrase: env::var("OKX_PASSPHRASE").ok(),
                enabled: true,
            });
        }
    }

    // Bybit
    if let Ok(key) = env::var("BYBIT_API_KEY") {
        if !key.is_empty() {
            configs.push(ExchangeConfig {
                id: ExchangeId::Bybit,
                api_key: key,
                api_secret: env::var("BYBIT_API_SECRET").unwrap_or_default(),
                passphrase: None,
                enabled: true,
            });
        }
    }

    // Gate.io
    if let Ok(key) = env::var("GATE_API_KEY") {
        if !key.is_empty() {
            configs.push(ExchangeConfig {
                id: ExchangeId::Gate,
                api_key: key,
                api_secret: env::var("GATE_API_SECRET").unwrap_or_default(),
                passphrase: None,
                enabled: true,
            });
        }
    }

    configs
}
