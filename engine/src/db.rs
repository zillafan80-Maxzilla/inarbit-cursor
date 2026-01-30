//! 数据库连接模块

use anyhow::Result;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;

use crate::config::{DatabaseConfig, RedisConfig};

/// 创建 PostgreSQL 连接池
pub async fn create_pool(config: &DatabaseConfig) -> Result<PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(20)
        .min_connections(5)
        .acquire_timeout(std::time::Duration::from_secs(30))
        .connect(&config.url())
        .await?;

    tracing::info!("PostgreSQL 连接池已创建");
    Ok(pool)
}

/// 创建 Redis 客户端
pub fn create_redis_client(config: &RedisConfig) -> Result<redis::Client> {
    let client = redis::Client::open(config.url())?;
    tracing::info!("Redis 客户端已创建");
    Ok(client)
}
