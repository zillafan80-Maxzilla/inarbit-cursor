"""
FastAPI 主应用入口 - 优化版V3
完整的路由注册、异常处理、日志配置、服务初始化
"""
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import DatabaseManager
from .services import ServiceContainer

# 创建logs目录
Path("logs").mkdir(exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/inarbit.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("=" * 60)
    logger.info("🚀 正在启动 Inarbit API Server V3.0...")
    logger.info("=" * 60)
    
    try:
        # 1. 初始化数据库连接
        logger.info("📊 初始化数据库连接...")
        db = DatabaseManager.get_instance()
        await db.initialize()
        logger.info("✅ 数据库连接初始化完成")
        
        # 2. 初始化服务容器
        logger.info("🔧 初始化服务容器...")
        ServiceContainer.initialize()
        logger.info("✅ 服务容器初始化完成")

        # 2.1 启动三角套利机会发现任务（会在首次扫描时播种交叉交易对）
        try:
            triangular_service = ServiceContainer.get_triangular_opportunity_service()
            await triangular_service.start()
            logger.info("✅ 三角套利机会服务已启动")
        except Exception as e:
            logger.warning(f"三角套利机会服务启动失败(可忽略但建议修复): {e}")

        # 2.2 启动行情采集后台任务
        try:
            market_data_service = ServiceContainer.get_market_data_service()
            await market_data_service.start()
            logger.info("✅ 行情采集服务已启动")
        except Exception as e:
            logger.warning(f"行情采集服务启动失败(可忽略但建议修复): {e}")

        # 2.3 启动期现套利机会发现任务
        try:
            cashcarry_service = ServiceContainer.get_cashcarry_opportunity_service()
            await cashcarry_service.start()
            logger.info("✅ 期现套利机会服务已启动")
        except Exception as e:
            logger.warning(f"期现套利机会服务启动失败(可忽略但建议修复): {e}")

        # 2.4 启动决策器/调度器
        try:
            decision_service = ServiceContainer.get_decision_service()
            await decision_service.start()
            logger.info("✅ 决策器服务已启动")
        except Exception as e:
            logger.warning(f"决策器服务启动失败(可忽略但建议修复): {e}")

        try:
            async with db.pg_connection() as conn:
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'"
                )
                await conn.execute(
                    "UPDATE users SET role = 'admin' WHERE username = 'admin' AND COALESCE(role, '') <> 'admin'"
                )
                await conn.execute(
                    "ALTER TABLE system_logs ADD COLUMN IF NOT EXISTS user_id UUID"
                )
                await conn.execute(
                    "UPDATE system_logs SET user_id = (extra->>'user_id')::uuid WHERE user_id IS NULL AND extra ? 'user_id'"
                )
        except Exception as e:
            logger.warning(f"Schema自修复失败(可忽略但建议修复): {e}")
        
        # 3. 初始化配置服务（如果需要）
        from .services.config_service import get_config_service
        config_service = await get_config_service()
        logger.info("✅ 配置服务初始化完成")
        
        logger.info("=" * 60)
        logger.info("🎉 Inarbit API Server 启动成功！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}", exc_info=True)
        raise
    
    yield
    
    # 清理资源
    logger.info("🔄 正在关闭 API Server...")
    try:
        try:
            market_data_service = ServiceContainer.get_market_data_service()
            await market_data_service.stop()
            logger.info("✅ 行情采集服务已停止")
        except Exception:
            pass
        try:
            triangular_service = ServiceContainer.get_triangular_opportunity_service()
            await triangular_service.stop()
            logger.info("✅ 三角套利机会服务已停止")
        except Exception:
            pass
        try:
            cashcarry_service = ServiceContainer.get_cashcarry_opportunity_service()
            await cashcarry_service.stop()
            logger.info("✅ 期现套利机会服务已停止")
        except Exception:
            pass
        try:
            decision_service = ServiceContainer.get_decision_service()
            await decision_service.stop()
            logger.info("✅ 决策器服务已停止")
        except Exception:
            pass
        await db.close()
        logger.info("✅ 数据库连接已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭时出错: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title="Inarbit HFT Trading System",
    description="高频交易系统 REST API - 支持模拟盘和实盘交易",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)


# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """统一异常处理"""
    logger.error(
        f"Unhandled exception at {request.method} {request.url.path}: {exc}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "服务器内部错误，请联系管理员",
            "path": str(request.url.path),
            "method": request.method
        }
    )


# 导入所有路由
from .api.routes import router as api_router
from .api.websocket import router as ws_router
from .api.config_routes import router as config_router
from .api.risk_routes import router as risk_router
from .api.system_routes import router as system_router
from .api.exchange_routes_v2 import router as exchange_v2_router
from .api.auth_routes import router as auth_router
from .api.arbitrage_routes import router as arbitrage_router
from .api.decision_routes import router as decision_router
from .api.oms_routes import router as oms_router
from .api.market_routes import router as market_router


# 注册路由 - 统一管理
logger.info("📡 注册API路由...")

app.include_router(api_router, prefix="/api/v1", tags=["V1 - Core API"])
app.include_router(risk_router, prefix="/api/v1/risk", tags=["V1 - Risk Management"])
app.include_router(config_router, prefix="/api/v1/config", tags=["V1 - Configuration"])
app.include_router(system_router, prefix="/api/v1/system", tags=["V1 - System"])
app.include_router(auth_router, tags=["V1 - Auth"])
app.include_router(arbitrage_router, tags=["V1 - Arbitrage"])
app.include_router(decision_router, tags=["V1 - Decision"])
app.include_router(oms_router, tags=["V1 - OMS"])
app.include_router(market_router, prefix="/api/v1", tags=["V1 - Market"])

# V2 路由（优化版）
app.include_router(exchange_v2_router, tags=["V2 - Exchanges"])

# WebSocket路由
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])


@app.get("/", tags=["Health Check"])
async def root():
    """根端点 - 服务状态"""
    return {
        "status": "running",
        "service": "Inarbit HFT Trading System",
        "version": "3.0.0",
        "api_docs": "/api/docs"
    }


@app.get("/health", tags=["Health Check"])
async def health_check():
    """详细健康检查 - 检查所有依赖服务"""
    db = DatabaseManager.get_instance()
    
    health_status = {
        "status": "healthy",
        "version": "3.0.0",
        "checks": {}
    }
    
    # 检查PostgreSQL
    try:
        async with db.pg_connection() as conn:
            await conn.fetchval("SELECT 1")
        health_status["checks"]["postgres"] = "connected"
    except Exception as e:
        health_status["checks"]["postgres"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # 检查Redis
    try:
        await db.redis.ping()
        health_status["checks"]["redis"] = "connected"
    except Exception as e:
        health_status["checks"]["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

