"""
简化的 FastAPI 启动脚本，用于诊断问题
"""
import logging
import sys
import traceback

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting minimal FastAPI server...")
    try:
        import uvicorn
        # 使用更简单的配置
        uvicorn.run(
            "server.app:app",
            host="127.0.0.1",
            port=8080,
            log_level="debug",
            reload=False,
            workers=1,
            loop="asyncio"
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
