import asyncio
import logging
from .strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)

class BaseStrategy:
    """
    所有策略的基类。
    """
    def __init__(self, engine: StrategyEngine, name: str):
        self.engine = engine
        self.name = name
        self.enabled = False

    async def run(self):
        """子类应重写此方法以实现具体的套利逻辑"""
        raise NotImplementedError("子类必须实现 run 方法")
