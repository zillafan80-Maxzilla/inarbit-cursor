import asyncio
import logging

class TriangularEngine:
    def __init__(self, exchange, paths, min_profit_threshold=0.001):
        """
        :param exchange: BaseExchange 实例
        :param paths: 列表，每个元素是一个元组 (A, B, C) 代表循环路径 A -> B -> C -> A
        :param min_profit_threshold: 触发交易的最小盈利阈值 (0.001 = 0.1%)
        """
        self.exchange = exchange
        self.paths = paths
        self.min_profit_threshold = min_profit_threshold
        self.logger = logging.getLogger("TriangularEngine")
        self.is_running = False

    async def start(self):
        self.is_running = True
        self.logger.info("三角套利引擎已启动")
        while self.is_running:
            try:
                tasks = [self.check_path(path) for path in self.paths]
                await asyncio.gather(*tasks)
                await asyncio.sleep(0.1) # 高频轮询间隔
            except Exception as e:
                self.logger.error(f"引擎循环异常: {e}")
                await asyncio.sleep(1)

    async def check_path(self, path):
        """
        路径示例: ('USDT', 'BTC', 'ETH')
        步骤:
        1. Buy BTC with USDT (BTC/USDT Ask) -> b_amount
        2. Buy ETH with BTC (ETH/BTC Ask)   -> c_amount
        3. Sell ETH for USDT (ETH/USDT Bid)  -> final_usdt
        """
        symbol1, symbol2, symbol3 = path # 这里的 path 实际上是币种名，如 USDT, BTC, ETH
        
        # 构造交易对名称
        pair1 = f"{symbol2}/{symbol1}" # BTC/USDT
        pair2 = f"{symbol3}/{symbol2}" # ETH/BTC
        pair3 = f"{symbol3}/{symbol1}" # ETH/USDT

        try:
            # 1. 抓取三个交易对的最新盘口
            tickers = await self.exchange.fetch_tickers([pair1, pair2, pair3])
            
            if not all(p in tickers for p in [pair1, pair2, pair3]):
                return

            tick1 = tickers[pair1]
            tick2 = tickers[pair2]
            tick3 = tickers[pair3]

            # 2. 计算利润 (由于是极速套利，我们看 Ask/Bid 而不是 Last Price)
            # 步骤 1: 用 USDT 买进 BTC (花费 1 USDT，得到 1 / tick1['ask'] BTC)
            btc_received = 1.0 / tick1['ask']
            
            # 步骤 2: 用 BTC 买进 ETH (得到 btc_received / tick2['ask'] ETH)
            eth_received = btc_received / tick2['ask']
            
            # 步骤 3: 把 ETH 换回 USDT (得到 eth_received * tick3['bid'] USDT)
            final_usdt = eth_received * tick3['bid']

            # 计算收益率
            profit = (final_usdt / 1.0) - 1.0

            if profit > self.min_profit_threshold:
                self.logger.info(f"💰 捕捉到信号! {symbol1}->{symbol2}->{symbol3} 收益率: {profit:.4%}")
                await self.execute_trade(path, profit)
                
        except Exception as e:
            self.logger.error(f"检查路径 {path} 出错: {e}")

    async def execute_trade(self, path, expected_profit):
        self.logger.info(f"正在执行套利交易: {path}")
        # 1. 连续下单逻辑
        # 2. 推送交易事件（日志记录）
        self.logger.info(f"交易事件: path={path}, expected_profit={expected_profit:.6f}")

    def stop(self):
        self.is_running = False
        self.logger.info("三角套利引擎已停止")
