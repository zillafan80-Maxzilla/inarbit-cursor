"""
仓位风险管理器
负责监控持仓敞口、执行止损止盈、控制最大回撤
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ExposureManager:
    """
    仓位风险管理器
    功能:
    1. 监控总敞口，防止过度杠杆
    2. 执行止损/止盈逻辑
    3. 控制最大回撤
    4. 限制单笔交易规模
    """
    
    def __init__(self, notifier=None):
        self.notifier = notifier
        
        # 风控参数 (遗留模块，使用静态配置)
        self.max_total_exposure = 10000.0  # 最大总敞口 (USDT)
        self.max_single_position = 1000.0  # 单笔最大持仓 (USDT)
        self.stop_loss_pct = 0.02  # 止损百分比 (2%)
        self.take_profit_pct = 0.05  # 止盈百分比 (5%)
        self.max_drawdown_pct = 0.10  # 最大回撤 (10%)
        self.daily_loss_limit = 500.0  # 每日最大亏损 (USDT)
        
        # 运行时状态
        self.positions: Dict[str, dict] = {}
        self.total_exposure = 0.0
        self.daily_pnl = 0.0
        self.peak_balance = 0.0
        self.current_balance = 0.0
        self.is_trading_halted = False
        self.halt_reason = ""
        
    def can_open_position(self, symbol: str, size_usdt: float) -> tuple[bool, str]:
        """
        检查是否允许开仓
        返回: (是否允许, 原因)
        """
        # 检查交易是否被暂停
        if self.is_trading_halted:
            return False, f"交易已暂停: {self.halt_reason}"
        
        # 检查每日亏损限制
        if self.daily_pnl <= -self.daily_loss_limit:
            self._halt_trading("已达每日最大亏损限制")
            return False, "已达每日最大亏损限制"
        
        # 检查单笔交易规模
        if size_usdt > self.max_single_position:
            return False, f"超出单笔最大持仓 ({size_usdt:.2f} > {self.max_single_position:.2f})"
        
        # 检查总敞口
        if self.total_exposure + size_usdt > self.max_total_exposure:
            return False, f"超出总敞口限制 ({self.total_exposure + size_usdt:.2f} > {self.max_total_exposure:.2f})"
        
        return True, "允许交易"
    
    def register_position(self, position_id: str, symbol: str, 
                          size_usdt: float, entry_price: float, 
                          direction: str) -> bool:
        """
        注册新仓位
        """
        allowed, reason = self.can_open_position(symbol, size_usdt)
        if not allowed:
            logger.warning(f"开仓被拒绝 [{symbol}]: {reason}")
            return False
        
        self.positions[position_id] = {
            'symbol': symbol,
            'size_usdt': size_usdt,
            'entry_price': entry_price,
            'direction': direction,
            'entry_time': datetime.now(),
            'stop_loss': self._calculate_stop_loss(entry_price, direction),
            'take_profit': self._calculate_take_profit(entry_price, direction),
        }
        
        self.total_exposure += size_usdt
        logger.info(f"仓位已注册: {position_id}, 当前总敞口: {self.total_exposure:.2f} USDT")
        return True
    
    def _calculate_stop_loss(self, entry_price: float, direction: str) -> float:
        """计算止损价格"""
        if direction == "long":
            return entry_price * (1 - self.stop_loss_pct)
        else:
            return entry_price * (1 + self.stop_loss_pct)
    
    def _calculate_take_profit(self, entry_price: float, direction: str) -> float:
        """计算止盈价格"""
        if direction == "long":
            return entry_price * (1 + self.take_profit_pct)
        else:
            return entry_price * (1 - self.take_profit_pct)
    
    def check_position(self, position_id: str, current_price: float) -> Optional[str]:
        """
        检查仓位是否触发止损/止盈
        返回: None=继续持有, "stop_loss"=止损, "take_profit"=止盈
        """
        pos = self.positions.get(position_id)
        if not pos:
            return None
        
        if pos['direction'] == "long":
            if current_price <= pos['stop_loss']:
                return "stop_loss"
            if current_price >= pos['take_profit']:
                return "take_profit"
        else:  # short
            if current_price >= pos['stop_loss']:
                return "stop_loss"
            if current_price <= pos['take_profit']:
                return "take_profit"
        
        return None
    
    def close_position(self, position_id: str, exit_price: float, pnl: float):
        """
        关闭仓位并更新状态
        """
        pos = self.positions.pop(position_id, None)
        if pos:
            self.total_exposure -= pos['size_usdt']
            self.daily_pnl += pnl
            self.current_balance += pnl
            
            # 更新峰值余额
            if self.current_balance > self.peak_balance:
                self.peak_balance = self.current_balance
            
            # 检查回撤
            self._check_drawdown()
            
            logger.info(f"仓位已关闭: {position_id}, PnL: {pnl:.2f} USDT, "
                       f"今日PnL: {self.daily_pnl:.2f} USDT")
    
    def _check_drawdown(self):
        """检查最大回撤"""
        if self.peak_balance <= 0:
            return
        
        drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
        if drawdown >= self.max_drawdown_pct:
            self._halt_trading(f"已达最大回撤限制 ({drawdown:.2%})")
    
    def _halt_trading(self, reason: str):
        """暂停交易"""
        self.is_trading_halted = True
        self.halt_reason = reason
        logger.warning(f"风控触发，交易已暂停: {reason}")
        
        # 可选通知器（若调用方提供）
        if self.notifier and hasattr(self.notifier, "push_log"):
            asyncio.create_task(self.notifier.push_log(f"[风控警报] {reason}", "ALERT"))
    
    def reset_daily_stats(self):
        """重置每日统计 (每日凌晨调用)"""
        self.daily_pnl = 0.0
        if self.is_trading_halted and "每日" in self.halt_reason:
            self.is_trading_halted = False
            self.halt_reason = ""
            logger.info("每日统计已重置，交易恢复")
    
    def update_config(self, config: dict):
        """动态更新风控配置"""
        if 'max_total_exposure' in config:
            self.max_total_exposure = config['max_total_exposure']
        if 'max_single_position' in config:
            self.max_single_position = config['max_single_position']
        if 'stop_loss_pct' in config:
            self.stop_loss_pct = config['stop_loss_pct']
        if 'take_profit_pct' in config:
            self.take_profit_pct = config['take_profit_pct']
        if 'max_drawdown_pct' in config:
            self.max_drawdown_pct = config['max_drawdown_pct']
        if 'daily_loss_limit' in config:
            self.daily_loss_limit = config['daily_loss_limit']
        
        logger.info(f"风控配置已更新: {config}")
    
    def get_status(self) -> dict:
        """获取当前风控状态"""
        return {
            'total_exposure': self.total_exposure,
            'max_total_exposure': self.max_total_exposure,
            'position_count': len(self.positions),
            'daily_pnl': self.daily_pnl,
            'current_balance': self.current_balance,
            'peak_balance': self.peak_balance,
            'is_halted': self.is_trading_halted,
            'halt_reason': self.halt_reason,
        }
