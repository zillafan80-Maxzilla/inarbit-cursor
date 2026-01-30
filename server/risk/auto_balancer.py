"""
自动平衡器
负责监控多交易所资产分布，执行自动调仓和资金再平衡
"""
import asyncio
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class AutoBalancer:
    """
    自动资产平衡器
    功能:
    1. 监控多交易所资产分布
    2. 当分布偏离目标时执行再平衡
    3. 支持内部转账和提现/充值建议
    """
    
    def __init__(self, exchanges: Dict = None, notifier=None):
        self.exchanges = exchanges or {}
        self.notifier = notifier
        
        # 平衡参数
        self.rebalance_threshold = 0.15  # 触发再平衡的偏离阈值 (15%)
        self.target_allocation = {
            'binance': 0.60,  # 60% 资产放在 Binance
            'okx': 0.30,      # 30% 资产放在 OKX
            'bybit': 0.10,    # 10% 资产放在 Bybit
        }
        self.min_rebalance_amount = 100.0  # 最小再平衡金额 (USDT)
        
        # 运行时状态
        self.last_rebalance_time = None
        self.is_running = False
        
    async def start(self, interval_minutes: int = 30):
        """启动自动平衡循环"""
        self.is_running = True
        logger.info("自动平衡器已启动")
        
        while self.is_running:
            try:
                await self._check_and_rebalance()
            except Exception as e:
                logger.error(f"自动平衡检查失败: {e}")
            
            await asyncio.sleep(interval_minutes * 60)
    
    async def stop(self):
        """停止自动平衡"""
        self.is_running = False
        logger.info("自动平衡器已停止")
    
    async def _check_and_rebalance(self):
        """检查并执行再平衡"""
        # 获取各交易所余额
        balances = await self._fetch_all_balances()
        if not balances:
            logger.warning("无法获取交易所余额，跳过本次平衡检查")
            return
        
        # 计算总资产和当前分配
        total_usdt = sum(balances.values())
        if total_usdt < self.min_rebalance_amount:
            logger.debug("总资产过低，跳过再平衡检查")
            return
        
        current_allocation = {ex: bal / total_usdt for ex, bal in balances.items()}
        
        # 检查偏离度
        rebalance_needed = []
        for exchange_id, target_pct in self.target_allocation.items():
            current_pct = current_allocation.get(exchange_id, 0)
            deviation = abs(current_pct - target_pct)
            
            if deviation > self.rebalance_threshold:
                diff_usdt = (target_pct - current_pct) * total_usdt
                rebalance_needed.append({
                    'exchange': exchange_id,
                    'current_pct': current_pct,
                    'target_pct': target_pct,
                    'deviation': deviation,
                    'diff_usdt': diff_usdt,  # 正数需转入，负数需转出
                })
        
        if rebalance_needed:
            await self._execute_rebalance(rebalance_needed, total_usdt)
    
    async def _fetch_all_balances(self) -> Dict[str, float]:
        """获取所有交易所的 USDT 余额"""
        balances = {}
        
        for exchange_id, exchange in self.exchanges.items():
            try:
                balance = await exchange.fetch_balance()
                usdt_free = balance.get('USDT', {}).get('free', 0) or 0
                usdt_used = balance.get('USDT', {}).get('used', 0) or 0
                balances[exchange_id] = usdt_free + usdt_used
            except Exception as e:
                logger.error(f"获取 {exchange_id} 余额失败: {e}")
        
        return balances
    
    async def _execute_rebalance(self, actions: List[dict], total_usdt: float):
        """
        执行再平衡操作
        注意: 实际的跨交易所转账需要提现/充值，这里仅生成建议
        """
        logger.info(f"检测到资产偏离，需要再平衡。总资产: {total_usdt:.2f} USDT")
        
        suggestions = []
        for action in actions:
            ex = action['exchange']
            diff = action['diff_usdt']
            
            if abs(diff) < self.min_rebalance_amount:
                continue
            
            if diff > 0:
                suggestion = f"向 {ex} 转入 {diff:.2f} USDT"
            else:
                suggestion = f"从 {ex} 转出 {abs(diff):.2f} USDT"
            
            suggestions.append(suggestion)
            logger.info(f"再平衡建议: {suggestion}")
        
        # 可选通知器（若调用方提供）
        if self.notifier and suggestions and hasattr(self.notifier, "push_log"):
            await self.notifier.push_log(
                f"[自动平衡] 建议执行: " + "; ".join(suggestions),
                "REBALANCE"
            )
        
        self.last_rebalance_time = datetime.now()
        return suggestions
    
    def update_target_allocation(self, new_allocation: Dict[str, float]):
        """更新目标分配比例"""
        total = sum(new_allocation.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"目标分配总和不为 1 ({total:.2f})，已自动归一化")
            new_allocation = {k: v / total for k, v in new_allocation.items()}
        
        self.target_allocation = new_allocation
        logger.info(f"目标分配已更新: {new_allocation}")
    
    def get_status(self) -> dict:
        """获取平衡器状态"""
        return {
            'is_running': self.is_running,
            'target_allocation': self.target_allocation,
            'rebalance_threshold': self.rebalance_threshold,
            'last_rebalance_time': str(self.last_rebalance_time) if self.last_rebalance_time else None,
        }
