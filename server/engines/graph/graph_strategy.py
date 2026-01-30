import logging
import math
import networkx as nx
from typing import List, Dict, Tuple
from ..base_strategy import BaseStrategy
from exchange.ccxt_exchange import CCXTExchange

logger = logging.getLogger(__name__)

class GraphSearchStrategy(BaseStrategy):
    """
    基于图搜索的通用套利策略。
    使用 Bellman-Ford 或者是简单的 DFS 寻找市场中的负权环 (即获利路径)。
    """
    def __init__(self, engine, exchange: CCXTExchange):
        super().__init__(engine, "GraphArbitrage")
        self.exchange = exchange
        self.graph = nx.DiGraph()
        self.min_profit = 0.001 # 0.1% 
        self.markets = {}

    async def run(self):
        logger.info("图搜索套利策略已启动...")
        # 1. 初始加载市场
        await self._build_market_graph()
        
        while self.engine.is_running:
            # 2. 更新价格 (在真实高频中，这里会由 WebSocket 回调驱动)
            await self._update_prices()
            
            # 3. 搜索路径
            opportunities = self._find_arbitrage_paths()
            
            # 4. 执行/记录
            for path in opportunities:
                await self._log_opportunity(path)
            
            # 模拟轮询间隔
            await asyncio.sleep(2)

    async def _build_market_graph(self):
        """构建初始交易对图谱"""
        try:
            # CCXT load_markets
            self.markets = await self.exchange.client.load_markets()
            logger.info(f"已加载 {len(self.markets)} 个交易对")
            
            # 构建节点和边 (Currency -> Currency)
            # 例如 BTC/USDT: 
            #   Edge(BTC -> USDT, weight=price) -- Sell
            #   Edge(USDT -> BTC, weight=1/price) -- Buy
            self.graph.clear()
            for symbol, market in self.markets.items():
                if not market['active']: continue
                base = market['base']
                quote = market['quote']
                
                # 初始化边，权重稍后更新
                self.graph.add_edge(base, quote, symbol=symbol, action='sell')
                self.graph.add_edge(quote, base, symbol=symbol, action='buy')
                
        except Exception as e:
            logger.error(f"构建市场图谱失败: {e}")

    async def _update_prices(self):
        """更新图中所有边的权重"""
        # 演示用：批量获取 Tickers
        if not self.markets: return
        
        # 优化：只选取 top 交易对或通过 websocket
        # 这里为了演示简单，我们只取部分重要交易对防止限频
        symbols = list(self.markets.keys())[:50] 
        tickers = await self.exchange.fetch_tickers(symbols)
        
        for symbol, ticker in tickers.items():
            if symbol not in self.markets: continue
            market = self.markets[symbol]
            base = market['base']
            quote = market['quote']
            
            # Ask Price (买入价) -> 这里的权重通常取 -log(rate) 用于寻找负权环
            # 但为了直观，我们先存储实际汇率，搜索时再计算
            
            if ticker['bid'] and ticker['bid'] > 0:
                # Sell base -> quote: get 'bid' amount of quote
                # weight = -math.log(ticker['bid'])
                self.graph[base][quote]['weight'] = -math.log(ticker['bid'])
                self.graph[base][quote]['rate'] = ticker['bid']

            if ticker['ask'] and ticker['ask'] > 0:
                 # Buy base <- quote: need 'ask' amount of quote logic...
                 # Actually: 1 Quote -> (1/Ask) Base
                 rate = 1.0 / ticker['ask']
                 self.graph[quote][base]['weight'] = -math.log(rate)
                 self.graph[quote][base]['rate'] = rate

    def _find_arbitrage_paths(self) -> List[Dict]:
        """使用 Bellman-Ford 寻找负权环"""
        opportunities = []
        # 由于 networkx 的 bellman_ford 通常用于单源最短路径，
        # 对于全图寻找负权环，我们可以用 negative_edge_cycle
        
        try:
            # 这是一个简单的寻找负权环的方法
            # 真实场景需要更高效的增量算法
            if nx.negative_edge_cycle(self.graph, weight='weight'):
                # 如果存在负权环，我们需要像 cycle_basis 那样找到具体的环
                # 这里为了简单，我们用 simple_cycles (很慢) 或者找一个源点
                # 实际生产代码通常自己写 spfa
                pass
                
            # fallback: 简单的 DFS 搜索固定长度的环 (3-4)
            # 这里演示一下寻找 USDT -> A -> B -> USDT 的路径
            start_node = 'USDT'
            if start_node not in self.graph: return []
            
            # 手动 DFS 找 3 跳回路
            for n1 in self.graph.neighbors(start_node):     # USDT -> n1
                for n2 in self.graph.neighbors(n1):         # n1 -> n2
                     if n2 == start_node: continue
                     if self.graph.has_edge(n2, start_node): # n2 -> USDT
                        # 找到环: USDT -> n1 -> n2 -> USDT
                        self._validate_path([start_node, n1, n2, start_node], opportunities)
                        
        except Exception as e:
            logger.error(f"搜索路径出错: {e}")
            
        return opportunities

    def _validate_path(self, nodes, opportunities):
        """
        验证路径盈利性 (Roibal Algorithm Refined)
        逻辑:
        1. 模拟初始资金在路径中流转 (Start Amount)
        2. 每一步扣除交易手续费 (Fee Rate, e.g. 0.075% or 0.1%)
        3. 计算最终资金与初始资金的差额
        """
        
        # 假设初始投入 1.0 单位的起始币种 (如 USDT)
        start_amount = 1.0
        current_amount = start_amount
        path_details = []
        fee_rate = 0.001 # 默认 0.1% 手续费 (Roibal 逻辑通常设为 0.0005~0.001)
        
        # 记录 Roibal 风格的 "Implied Rate" 所需数据
        # 但在 Graph 搜索中，我们直接模拟资金流更准确
        
        valid = True
        for i in range(len(nodes)-1):
            u, v = nodes[i], nodes[i+1]
            edge = self.graph[u][v]
            
            if 'rate' not in edge: 
                valid = False
                break
                
            rate = edge['rate']
            action = edge.get('action', 'trade')
            
            # Roibal Step Logic: Amount * Price * (1 - Fee)
            # 注意: 如果是 Sell (Base->Quote)，rate是 bid (价格)。Amount * Rate
            # 如果是 Buy (Quote->Base)，rate是 1/ask (汇率)。Amount * Rate 
            # 这里的 self.graph 中的 'rate' 已经是转换汇率了 (1/ask or bid)
            
            amount_before_fee = current_amount * rate
            current_amount = amount_before_fee * (1 - fee_rate)
            
            path_details.append(f"{u}->{v}@{rate:.4f}")

        if not valid: return

        # 计算净利润率
        gross_profit = (current_amount - start_amount) / start_amount
        
        # Roibal 的阈值通常包含滑点保护，这里设为 0.2%
        if gross_profit > 0.002: 
             opp = {
                 'path': path_details,
                 'profit': gross_profit,
                 'roibal_logic': True,
                 'start_coin': nodes[0],
                 'steps': len(nodes) - 1
             }
             opportunities.append(opp)

    async def _log_opportunity(self, opp):
        """记录"""
        path_str = " -> ".join(opp['path'])
        logger.info(f"图搜索发现机会: {path_str}, 预期收益: {opp['profit']:.4%}")

import asyncio
