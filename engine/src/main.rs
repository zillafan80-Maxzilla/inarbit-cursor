mod config;
mod db;
mod exchange;
mod executor;
mod risk;
mod strategy;

use std::time::Duration;

use anyhow::Result;
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

use crate::config::load_config;
use crate::db::{create_pool, create_redis_client};
use crate::exchange::connect_all;
use crate::executor::OrderExecutor;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let config = load_config()?;

    let _pool = match create_pool(&config.database).await {
        Ok(pool) => Some(pool),
        Err(err) => {
            warn!("db connection failed, continue without postgres: {}", err);
            None
        }
    };

    let redis = match create_redis_client(&config.redis) {
        Ok(client) => Some(client),
        Err(err) => {
            warn!("redis connection failed, continue without redis: {}", err);
            None
        }
    };

    let connections = connect_all(&config.exchanges).await?;
    let mut executor = OrderExecutor::new(connections, redis);
    executor.set_simulation_mode(config.mode != "live");

    info!("inarbit engine started (mode: {})", config.mode);

    loop {
        tokio::time::sleep(Duration::from_secs(60)).await;
    }
}
