"""
服务容器 - 统一管理所有服务实例
使用单例模式，避免重复创建，便于依赖注入和测试
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    服务容器 - 依赖注入容器
    管理所有服务的单例实例
    """
    
    # 服务实例
    _exchange_service: Optional['ExchangeService'] = None
    _order_service: Optional['OrderService'] = None
    _pnl_service: Optional['PnLService'] = None
    _market_data_service: Optional['MarketDataService'] = None
    _triangular_opportunity_service: Optional['TriangularOpportunityService'] = None
    _cashcarry_opportunity_service: Optional['CashCarryOpportunityService'] = None
    _decision_service: Optional['DecisionService'] = None
    _market_regime_service: Optional['MarketRegimeService'] = None
    
    @classmethod
    def initialize(cls):
        """
        初始化所有服务
        在应用启动时调用
        """
        logger.info("🔧 初始化服务容器...")
        
        # 延迟导入避免循环依赖
        from .exchange_service import ExchangeService
        from .order_service import OrderService, PnLService
        from .market_data_service import MarketDataService
        from .triangular_opportunity_service import TriangularOpportunityService
        from .cashcarry_opportunity_service import CashCarryOpportunityService
        from .decision_service import DecisionService
        from .market_regime_service import MarketRegimeService
        
        cls._exchange_service = ExchangeService()
        cls._order_service = OrderService()
        cls._pnl_service = PnLService()
        cls._market_data_service = MarketDataService()
        cls._triangular_opportunity_service = TriangularOpportunityService()
        cls._cashcarry_opportunity_service = CashCarryOpportunityService()
        cls._decision_service = DecisionService()
        cls._market_regime_service = MarketRegimeService()
        
        logger.info("✅ 服务容器初始化完成")
    
    @classmethod
    def get_exchange_service(cls):
        """获取交易所服务"""
        if cls._exchange_service is None:
            from .exchange_service import ExchangeService
            cls._exchange_service = ExchangeService()
        return cls._exchange_service
    
    @classmethod
    def get_order_service(cls):
        """获取订单服务"""
        if cls._order_service is None:
            from .order_service import OrderService
            cls._order_service = OrderService()
        return cls._order_service
    
    @classmethod
    def get_pnl_service(cls):
        """获取收益服务"""
        if cls._pnl_service is None:
            from .order_service import PnLService
            cls._pnl_service = PnLService()
        return cls._pnl_service

    @classmethod
    def get_market_data_service(cls):
        """获取行情服务"""
        if cls._market_data_service is None:
            from .market_data_service import MarketDataService
            cls._market_data_service = MarketDataService()
        return cls._market_data_service
    
    @classmethod
    def get_triangular_opportunity_service(cls):
        """获取三角套利机会服务"""
        if cls._triangular_opportunity_service is None:
            from .triangular_opportunity_service import TriangularOpportunityService
            cls._triangular_opportunity_service = TriangularOpportunityService()
        return cls._triangular_opportunity_service
    
    @classmethod
    def get_cashcarry_opportunity_service(cls):
        """获取期现套利机会服务"""
        if cls._cashcarry_opportunity_service is None:
            from .cashcarry_opportunity_service import CashCarryOpportunityService
            cls._cashcarry_opportunity_service = CashCarryOpportunityService()
        return cls._cashcarry_opportunity_service
    
    @classmethod
    def get_decision_service(cls):
        """获取决策服务"""
        if cls._decision_service is None:
            from .decision_service import DecisionService
            cls._decision_service = DecisionService()
        return cls._decision_service

    @classmethod
    def get_market_regime_service(cls):
        """获取市场状态服务"""
        if cls._market_regime_service is None:
            from .market_regime_service import MarketRegimeService
            cls._market_regime_service = MarketRegimeService()
        return cls._market_regime_service
    
    @classmethod
    def reset(cls):
        """
        重置服务容器
        主要用于测试
        """
        cls._exchange_service = None
        cls._order_service = None
        cls._pnl_service = None
        cls._market_data_service = None
        cls._triangular_opportunity_service = None
        cls._cashcarry_opportunity_service = None
        cls._decision_service = None
        cls._market_regime_service = None


# 导出所有服务
from .exchange_service import ExchangeService
from .order_service import OrderService, PnLService
from .market_data_service import MarketDataService
from .market_data_repository import MarketDataRepository
from .triangular_opportunity_service import TriangularOpportunityService
from .cashcarry_opportunity_service import CashCarryOpportunityService
from .decision_service import DecisionService
from .oms_service import OmsService
from .market_regime_service import MarketRegimeService

def get_decision_service():
    """快捷获取决策服务实例"""
    return ServiceContainer.get_decision_service()

__all__ = [
    "ServiceContainer",
    "ConfigService",
    "MarketDataService",
    "MarketDataRepository",
    "TriangularOpportunityService",
    "CashCarryOpportunityService",
    "DecisionService",
    "OmsService",
    "MarketRegimeService",
    "get_decision_service",
]
