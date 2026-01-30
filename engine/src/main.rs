//! Inarbit 高性能套利引擎
//! 
//! 核心模块:
//! - exchange: 多交易所 WebSocket 连接
//! - strategy: 策略引擎框架
//! - executor: 订单执行引擎

mod exchange;
mod strategy;
mod executor;
mod config;
mod db;
mod risk;

use anyhow::Result;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

#[tokio::main]
async fn main() -> Result<()> {
    // 初始化日志
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .finish();
    tracing::subscriber::set_global_default(subscriber)?;

    info!("==================================================");
    info!("       Inarbit HFT Engine v0.1.0");
    info!("==================================================");

    // 加载配置
    dotenv::dotenv().ok();
    let config = config::load_config()?;
    
    info!("配置加载完成");
    info!("模式: {}", config.mode);

    let mode = config.mode.to_lowercase();
    if mode == "live" {
        let execute_signals = std::env::var("ENGINE_EXECUTE_SIGNALS")
            .map(|v| matches!(v.as_str(), "1" | "true" | "True"))
            .unwrap_or(false);
        let live_confirm = std::env::var("ENGINE_LIVE_CONFIRM").unwrap_or_default();
        if !execute_signals || live_confirm != "CONFIRM_LIVE" {
            return Err(anyhow::anyhow!(
                "live mode blocked: require ENGINE_EXECUTE_SIGNALS=1 and ENGINE_LIVE_CONFIRM=CONFIRM_LIVE"
            ));
        }
    }

    // 初始化数据库连接
    let db_pool = db::create_pool(&config.database).await?;
    let redis_client = db::create_redis_client(&config.redis)?;
    
    info!("数据库连接已建立");

    // 初始化交易所连接
    let exchanges = exchange::connect_all(&config.exchanges).await?;
    info!("已连接 {} 个交易所", exchanges.len());

    // 初始化策略引擎
    let mut strategy_engine = strategy::Engine::new(db_pool.clone(), redis_client.clone());
    
    // 加载启用的策略
    strategy_engine.load_enabled_strategies().await?;
    info!("已加载 {} 个策略", strategy_engine.strategy_count());

    // 初始化执行引擎
    let mut executor = executor::OrderExecutor::new(exchanges.clone());
    executor.set_simulation_mode(mode != "live");

    // 启动主循环
    info!("引擎启动完成，开始运行...");

    // [DEBUG] 启动心跳日志任务 (用于前端验证)
    let redis_client_clone = redis_client.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(5));
        loop {
            interval.tick().await;
            
            // 获取连接并发布消息
            // 使用多路复用连接，兼容新版 redis 客户端
            if let Ok(mut con) = redis_client_clone.get_multiplexed_async_connection().await {
                use redis::AsyncCommands;
                let msg = serde_json::json!({
                    "level": "INFO",
                    "source": "engine",
                    "message": format!("Engine Heartbeat: {}", chrono::Local::now().format("%H:%M:%S")),
                    "created_at": chrono::Utc::now().to_rfc3339()
                }).to_string();

                if let Err(e) = con.publish::<_, _, ()>("log:info", msg).await {
                    tracing::error!("Redis publish error: {}", e);
                }
            }
        }
    });
    
    // 运行策略引擎
    tokio::select! {
        result = strategy_engine.run(exchanges, &executor) => {
            if let Err(e) = result {
                tracing::error!("策略引擎错误: {}", e);
            }
        }
        _ = tokio::signal::ctrl_c() => {
            info!("收到停止信号，正在关闭...");
        }
    }

    // 清理资源
    strategy_engine.shutdown().await;
    info!("引擎已停止");

    Ok(())
}
