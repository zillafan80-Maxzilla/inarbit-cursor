"""
高级套利算法实现
包括: Bellman-Ford 图搜索、资金费率套利等
"""

import logging
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """套利机会"""
    type: str  # 'triangular', 'graph', 'funding_rate'
    symbols: List[str]
    path: str  # 交易路径，如: "BTC/USDT -> ETH/USDT -> BTC/ETH"
    entry_prices: Dict[str, float]
    exit_prices: Dict[str, float]
    expected_profit: float  # 绝对收益
    expected_profit_rate: float  # 收益率 (%)
    confidence: float  # 信心度 (0-1)
    execution_time_ms: int  # 预期执行时间
    timestamp: datetime


class BellmanFordGraph:
    """
    Bellman-Ford 最短路径图
    用于发现负权环（套利机会）
    """
    
    def __init__(self):
        self.graph: Dict[str, Dict[str, float]] = defaultdict(dict)
        self.nodes: List[str] = []
    
    def add_edge(self, from_node: str, to_node: str, weight: float) -> None:
        """
        添加有向边
        weight: 日志收益率 (负表示亏损)
        """
        if from_node not in self.nodes:
            self.nodes.append(from_node)
        if to_node not in self.nodes:
            self.nodes.append(to_node)
        
        self.graph[from_node][to_node] = weight
    
    def bellman_ford(self, start_node: str) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
        """
        执行 Bellman-Ford 算法
        返回: (最短距离字典, 父节点字典)
        """
        distances = {node: float('inf') for node in self.nodes}
        parents = {node: None for node in self.nodes}
        distances[start_node] = 0.0
        
        # 松弛 n-1 次
        for _ in range(len(self.nodes) - 1):
            for from_node in self.graph:
                if distances[from_node] != float('inf'):
                    for to_node, weight in self.graph[from_node].items():
                        new_dist = distances[from_node] + weight
                        if new_dist < distances[to_node]:
                            distances[to_node] = new_dist
                            parents[to_node] = from_node
        
        return distances, parents
    
    def find_negative_cycles(self) -> List[List[str]]:
        """
        发现所有负权环（套利机会）
        负权环表示存在可盈利的套利路径
        """
        negative_cycles = []
        
        for start_node in self.nodes:
            distances, parents = self.bellman_ford(start_node)
            
            # 第n次松弛，检查是否还能改进（表示有负权环）
            for from_node in self.graph:
                if distances[from_node] != float('inf'):
                    for to_node, weight in self.graph[from_node].items():
                        if distances[from_node] + weight < distances[to_node]:
                            # 发现负权环，回溯完整路径
                            cycle = self._extract_cycle(to_node, parents, start_node)
                            if cycle and cycle not in negative_cycles:
                                negative_cycles.append(cycle)
        
        return negative_cycles
    
    def _extract_cycle(self, node: str, parents: Dict[str, Optional[str]], 
                       start_node: str) -> Optional[List[str]]:
        """
        从图中回溯提取完整的环路
        """
        visited = set()
        current = node
        
        # 回溯找到环的起点
        while current is not None and current not in visited:
            visited.add(current)
            current = parents.get(current)
        
        if current is None:
            return None
        
        # 提取完整环
        cycle = [current]
        prev = current
        while True:
            current = parents.get(prev)
            if current is None or current == cycle[0]:
                break
            cycle.append(current)
            prev = current
        
        return cycle if len(cycle) > 1 else None


class FundingRateArbitrage:
    """
    资金费率套利
    现货做多 + 永续做空 = 无方向风险，获取资金费收益
    """
    
    def __init__(self):
        self.min_funding_rate = 0.0005  # 最小资金费率阈值 (0.05%)
        self.min_basis = 0.001  # 最小基差 (0.1%)
        self.spot_prices: Dict[str, float] = {}
        self.futures_prices: Dict[str, float] = {}
        self.funding_rates: Dict[str, float] = {}
    
    def update_prices(self, symbol: str, spot_price: float, futures_price: float,
                     funding_rate: float) -> None:
        """更新行情数据"""
        self.spot_prices[symbol] = spot_price
        self.futures_prices[symbol] = futures_price
        self.funding_rates[symbol] = funding_rate
    
    def find_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        发现资金费率套利机会
        逻辑: 如果资金费率为正且大于基差，则存在套利机会
        """
        opportunities = []
        
        for symbol in self.spot_prices:
            if symbol not in self.futures_prices:
                continue
            
            spot_price = self.spot_prices[symbol]
            futures_price = self.futures_prices[symbol]
            funding_rate = self.funding_rates.get(symbol, 0.0)
            
            if spot_price <= 0 or futures_price <= 0:
                continue
            
            # 计算基差
            basis = (futures_price - spot_price) / spot_price
            
            # 套利条件: 资金费率 > 基差 + 成本
            cost = 0.002  # 预计成本 (交易费、滑点等)
            profit_rate = funding_rate - basis - cost
            
            if profit_rate > self.min_funding_rate:
                opportunities.append(ArbitrageOpportunity(
                    type='funding_rate',
                    symbols=[symbol],
                    path=f"{symbol}(Spot) + {symbol}(Futures)",
                    entry_prices={f"{symbol}_spot": spot_price, f"{symbol}_futures": futures_price},
                    exit_prices={f"{symbol}_spot": spot_price, f"{symbol}_futures": futures_price},
                    expected_profit=profit_rate * spot_price,  # 单位:USDT
                    expected_profit_rate=profit_rate * 100,  # 百分比
                    confidence=0.95,
                    execution_time_ms=500,
                    timestamp=datetime.now()
                ))
                
                logger.debug(
                    f"发现资金费率套利: {symbol}, "
                    f"费率={funding_rate:.4%}, 基差={basis:.4%}, "
                    f"预期收益={profit_rate:.4%}"
                )
        
        return opportunities
    
    def calculate_position_size(self, symbol: str, account_equity: float,
                               max_exposure: float = 0.1) -> float:
        """
        根据账户权益计算头寸大小
        max_exposure: 最大敞口比例 (默认10%)
        """
        if symbol not in self.spot_prices:
            return 0.0
        
        price = self.spot_prices[symbol]
        if price <= 0:
            return 0.0
        
        # 头寸价值 = 账户权益 × 最大敞口比例
        position_value = account_equity * max_exposure
        position_size = position_value / price
        
        return position_size


class TriangularArbitrage:
    """
    三角套利
    A -> B -> C -> A 的循环交易
    """
    
    def __init__(self):
        self.min_profit_rate = 0.001  # 最小收益率 (0.1%)
        self.prices: Dict[str, float] = {}
        self.fees: Dict[str, float] = {}  # symbol -> 交易费率
    
    def update_price(self, symbol: str, price: float, fee: float = 0.001) -> None:
        """更新交易对价格"""
        self.prices[symbol] = price
        self.fees[symbol] = fee
    
    def find_triangular_opportunities(self, 
                                      symbol_a: str, symbol_b: str, symbol_c: str,
                                      initial_amount: float = 1000.0) -> Optional[ArbitrageOpportunity]:
        """
        检查三角套利机会
        路径: A -> B -> C -> A
        
        示例:
        - symbol_a = "BTC/USDT"
        - symbol_b = "ETH/USDT"
        - symbol_c = "ETH/BTC"
        
        执行步骤:
        1. 用1000 USDT买入BTC (BTC/USDT)
        2. 用得到的BTC买入ETH (ETH/BTC)
        3. 用得到的ETH兑换回USDT (ETH/USDT)
        """
        
        if symbol_a not in self.prices or symbol_b not in self.prices or symbol_c not in self.prices:
            return None
        
        try:
            # 路径1: A -> B -> C -> A
            # 步骤1: 用 initial_amount 买入 symbol_a
            price_a = self.prices[symbol_a]
            fee_a = self.fees.get(symbol_a, 0.001)
            amount_a = initial_amount / price_a * (1 - fee_a)
            
            # 步骤2: 用 amount_a 买入 symbol_b
            price_b = self.prices[symbol_b]
            fee_b = self.fees.get(symbol_b, 0.001)
            # symbol_b 如果是 B/USDT，需要用 USDT 购买
            # 但我们有 A，所以需要通过 C 转换
            
            # 步骤3: 通过 symbol_c (C/A) 交换
            price_c = self.prices[symbol_c]
            fee_c = self.fees.get(symbol_c, 0.001)
            
            # 简化计算: 假设直接路径
            final_amount = amount_a * price_c * (1 - fee_c) * price_b * (1 - fee_b)
            
            profit = final_amount - initial_amount
            profit_rate = profit / initial_amount
            
            if profit_rate > self.min_profit_rate:
                return ArbitrageOpportunity(
                    type='triangular',
                    symbols=[symbol_a, symbol_b, symbol_c],
                    path=f"{symbol_a} -> {symbol_b} -> {symbol_c} -> {symbol_a}",
                    entry_prices={symbol_a: price_a, symbol_b: price_b, symbol_c: price_c},
                    exit_prices={symbol_a: price_a, symbol_b: price_b, symbol_c: price_c},
                    expected_profit=profit,
                    expected_profit_rate=profit_rate * 100,
                    confidence=0.85,
                    execution_time_ms=1000,
                    timestamp=datetime.now()
                )
        except Exception as e:
            logger.error(f"三角套利计算异常: {e}")
        
        return None


class MultiHopArbitrage:
    """
    多跳套利 (N跳)
    通用的路径搜索和收益计算
    """
    
    def __init__(self, min_profit_rate: float = 0.001):
        self.min_profit_rate = min_profit_rate
        self.prices: Dict[str, float] = {}
        self.fees: Dict[str, float] = {}
    
    def update_price(self, symbol: str, price: float, fee: float = 0.001) -> None:
        """更新价格"""
        self.prices[symbol] = price
        self.fees[symbol] = fee
    
    def calculate_path_profit(self, path: List[str], initial_amount: float = 1.0) -> Tuple[float, float]:
        """
        计算路径收益
        返回: (最终金额, 收益率)
        """
        amount = initial_amount
        
        for symbol in path:
            if symbol not in self.prices:
                return 0.0, 0.0
            
            price = self.prices[symbol]
            fee = self.fees.get(symbol, 0.001)
            amount = amount / price * (1 - fee)
        
        profit_rate = (amount - initial_amount) / initial_amount
        return amount, profit_rate
    
    def find_best_paths(self, max_hops: int = 4, 
                       start_currency: str = "USDT") -> List[Tuple[List[str], float]]:
        """
        使用深度优先搜索找到最优的多跳套利路径
        返回: [(路径列表, 收益率)]
        """
        best_paths = []
        
        def dfs(current_symbol: str, path: List[str], visited: set, depth: int):
            if depth > max_hops:
                return
            
            # 如果回到起点且路径长度>1，检查收益
            if current_symbol == start_currency and len(path) > 1:
                _, profit_rate = self.calculate_path_profit(path)
                if profit_rate > self.min_profit_rate:
                    best_paths.append((path.copy(), profit_rate))
                return
            
            # 继续搜索
            for next_symbol in self.prices.keys():
                if next_symbol not in visited or next_symbol == start_currency:
                    if next_symbol != start_currency or len(path) > 2:
                        new_visited = visited.copy()
                        new_visited.add(next_symbol)
                        dfs(next_symbol, path + [next_symbol], new_visited, depth + 1)
        
        dfs(start_currency, [start_currency], {start_currency}, 0)
        
        # 排序:按收益率降序
        best_paths.sort(key=lambda x: x[1], reverse=True)
        
        return best_paths[:10]  # 返回前10个最优路径


def detect_arbitrage_opportunities(
    prices: Dict[str, float],
    fees: Dict[str, float],
    account_equity: float,
    funding_rates: Optional[Dict[str, float]] = None
) -> Dict[str, List[ArbitrageOpportunity]]:
    """
    综合套利机会检测
    返回: {
        'triangular': [三角套利机会],
        'funding_rate': [资金费率套利机会],
        'graph': [图搜索套利机会]
    }
    """
    opportunities = {
        'triangular': [],
        'funding_rate': [],
        'graph': []
    }
    
    try:
        # 三角套利检测
        triangular = TriangularArbitrage()
        for symbol, price in prices.items():
            fee = fees.get(symbol, 0.001)
            triangular.update_price(symbol, price, fee)
        
        # 这里可以添加更多三角套利检测逻辑
        
        # 资金费率套利检测
        if funding_rates:
            fr_arb = FundingRateArbitrage()
            for symbol, funding_rate in funding_rates.items():
                if symbol in prices:
                    # 需要同时有现货和期货价格
                    # 这里简化处理
                    fr_arb.update_prices(symbol, prices[symbol], prices[symbol], funding_rate)
            
            opportunities['funding_rate'] = fr_arb.find_opportunities()
        
        # 图搜索检测（Bellman-Ford）
        # 构建图：节点=交易对，边=交易关系，权重=日志收益率
        
    except Exception as e:
        logger.error(f"套利检测异常: {e}", exc_info=True)
    
    return opportunities
