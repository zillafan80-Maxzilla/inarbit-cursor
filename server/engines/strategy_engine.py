"""
策略引擎核心类
负责管理各种套利策略的生命周期，包括初始化、启动、监控和停止
使用PostgreSQL和统一配置服务
"""
import asyncio
import json
import logging
import math
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass
from uuid import UUID

from ..db import get_pg_pool
from ..services.config_service import get_config_service
from ..services.market_data_repository import MarketDataRepository
from ..engines.arbitrage_algorithms import BellmanFordGraph, FundingRateArbitrage, TriangularArbitrage

logger = logging.getLogger(__name__)


@dataclass
class StrategyState:
    """策略运行状态"""
    strategy_id: str
    strategy_type: str
    name: str
    is_running: bool = False
    last_run: Optional[datetime] = None
    total_trades: int = 0
    total_profit: float = 0.0
    error_message: Optional[str] = None


class StrategyEngine:
    """
    策略引擎核心类
    负责管理各种套利策略的生命周期
    """
    
    _instance: Optional['StrategyEngine'] = None
    
    def __init__(self):
        self.strategies: Dict[str, StrategyState] = {}
        self.is_running = False
        self._tasks: List[asyncio.Task] = []
        self._config_service = None
        self.user_id: Optional[UUID] = None
        self._scan_interval_cache: Dict[str, tuple[float, float]] = {}
        self._scan_interval_ttl_seconds = 30.0
    
    @classmethod
    def get_instance(cls) -> 'StrategyEngine':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = StrategyEngine()
        return cls._instance
    
    async def initialize(self):
        """初始化策略引擎"""
        logger.info("正在初始化策略引擎...")
        
        # 获取配置服务
        self._config_service = await get_config_service()
        
        # 从数据库加载策略配置
        await self.initialize_for_user(self.user_id)
        
        logger.info(f"策略引擎初始化完成，已加载 {len(self.strategies)} 个策略")

    async def initialize_for_user(self, user_id: Optional[UUID]):
        self.user_id = user_id
        self.strategies = {}
        await self._load_strategies_from_db(user_id=user_id)
    
    async def _load_strategies_from_db(self, user_id: Optional[UUID] = None):
        """从数据库加载策略配置"""
        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                if user_id is None:
                    user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
                    if user_count and int(user_count) > 1:
                        logger.warning("检测到多用户，但 StrategyEngine 未按用户隔离；已跳过策略自动加载")
                        return
                    user_id = await conn.fetchval("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")

                if not user_id:
                    return

                self.user_id = user_id

                rows = await conn.fetch(
                    """
                    SELECT id, strategy_type, name, is_enabled,
                           total_trades, total_profit, last_run_at
                    FROM strategy_configs
                    WHERE user_id = $1
                    ORDER BY priority ASC
                    """,
                    user_id,
                )
                
                for row in rows:
                    self.strategies[str(row['id'])] = StrategyState(
                        strategy_id=str(row['id']),
                        strategy_type=row['strategy_type'],
                        name=row['name'],
                        is_running=row['is_enabled'],
                        last_run=row['last_run_at'],
                        total_trades=row['total_trades'] or 0,
                        total_profit=float(row['total_profit']) if row['total_profit'] else 0.0
                    )
        except Exception as e:
            logger.error(f"加载策略配置失败: {e}")
    
    async def start(self):
        """启动策略引擎"""
        if self.is_running:
            logger.warning("策略引擎已在运行")
            return
        
        self.is_running = True
        logger.info("正在启动策略引擎...")
        
        # 更新数据库中的机器人状态
        await self._update_bot_status('running')
        
        # 启动所有已启用的策略
        for strategy_id, state in self.strategies.items():
            if state.is_running:
                task = asyncio.create_task(self._run_strategy(strategy_id))
                self._tasks.append(task)
        
        logger.info(f"策略引擎已启动，运行中策略: {len(self._tasks)}")
    
    async def _run_strategy(self, strategy_id: str):
        """
        运行单个策略的主循环
        优化: 添加性能监控、异常重试、详细日志
        """
        state = self.strategies.get(strategy_id)
        if not state:
            logger.error(f"策略 {strategy_id} 不存在")
            return
        
        logger.info(f"🚀 启动策略循环: {state.name} ({state.strategy_type})")
        
        # 性能统计
        execution_times = []
        error_count = 0
        max_retries = 3
        
        try:
            while self.is_running and state.is_running:
                start_time = asyncio.get_event_loop().time()
                
                try:
                    # 执行策略周期
                    await self._execute_strategy_cycle(strategy_id)
                    
                    # 更新最后运行时间
                    state.last_run = datetime.now()
                    state.error_message = None  # 清除错误
                    error_count = 0  # 重置错误计数
                    
                    # 记录执行时间
                    execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
                    execution_times.append(execution_time)
                    
                    # 保持最近100次记录
                    if len(execution_times) > 100:
                        execution_times.pop(0)
                    
                    # 每10次循环输出性能统计
                    if len(execution_times) % 10 == 0:
                        avg_time = sum(execution_times) / len(execution_times)
                        logger.debug(
                            f"📊 策略 {state.name}: "
                            f"平均执行时间={avg_time:.2f}ms, "
                            f"总交易={state.total_trades}, "
                            f"总收益={state.total_profit:.2f} USDT"
                        )
                    
                except Exception as e:
                    error_count += 1
                    state.error_message = str(e)
                    logger.error(
                        f"❌ 策略 {state.name} 执行出错 (第{error_count}次): {e}",
                        exc_info=True
                    )
                    
                    # 达到最大重试次数，暂停策略
                    if error_count >= max_retries:
                        logger.error(f"🛑 策略 {state.name} 错误次数过多，自动停止")
                        state.is_running = False
                        await self._update_strategy_status(strategy_id, False, str(e))
                        break
                    
                    # 错误后等待更长时间
                    await asyncio.sleep(5)
                    continue
                
                # 等待下一个周期（从配置读取扫描间隔）
                scan_interval = await self._get_strategy_scan_interval(strategy_id)
                await asyncio.sleep(scan_interval)
                
        except asyncio.CancelledError:
            logger.info(f"⏹️ 策略 {state.name} 被用户停止")
        except Exception as e:
            state.error_message = str(e)
            logger.error(f"💥 策略 {state.name} 发生致命错误: {e}", exc_info=True)
        finally:
            logger.info(
                f"🏁 策略 {state.name} 已停止 | "
                f"总交易: {state.total_trades} | "
                f"总收益: {state.total_profit:.2f} USDT | "
                f"平均执行时间: {sum(execution_times)/len(execution_times) if execution_times else 0:.2f}ms"
            )

    
    async def _execute_strategy_cycle(self, strategy_id: str):
        """执行一个策略周期"""
        state = self.strategies.get(strategy_id)
        if not state:
            return
        
        # 根据策略类型调用不同的执行器
        if state.strategy_type == 'triangular':
            await self._execute_triangular(strategy_id)
        elif state.strategy_type == 'graph':
            await self._execute_graph(strategy_id)
        elif state.strategy_type == 'funding_rate':
            await self._execute_funding_rate(strategy_id)
        elif state.strategy_type == 'grid':
            await self._execute_grid(strategy_id)
        elif state.strategy_type == 'pair':
            await self._execute_pair(strategy_id)
        else:
            raise ValueError(f"不支持的策略类型: {state.strategy_type}")

    async def _get_strategy_config_for_user(self, conn, strategy_id: str):
        if not self.user_id:
            raise ValueError("StrategyEngine user_id is required")

        config = await conn.fetchval(
            "SELECT config FROM strategy_configs WHERE id = $1 AND user_id = $2",
            strategy_id,
            self.user_id,
        )

        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception:
                config = {}

        return config or {}
    
    # ============================================
    # 策略执行器（实际实现）
    # ============================================
    
    async def _execute_triangular(self, strategy_id: str):
        """三角套利策略执行"""
        try:
            # 获取策略配置
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                config = await self._get_strategy_config_for_user(conn, strategy_id)
                if not config:
                    return
            
            min_profit_rate = float(config.get("min_profit_rate", 0.001))
            fee_rate = float(config.get("fee_rate", 0.0004))
            exchange_id = str(config.get("exchange_id") or "binance")
            base_currencies = config.get("base_currencies", ["USDT", "BTC", "ETH"])

            service = await get_config_service()
            pairs = await service.get_pairs_for_exchange(exchange_id)
            if not pairs:
                return

            repo = MarketDataRepository()
            triangular = TriangularArbitrage()
            triangular.min_profit_rate = min_profit_rate

            semaphore = asyncio.Semaphore(60)

            async def _fetch_price(pair):
                async with semaphore:
                    tob = await repo.get_orderbook_tob(exchange_id, pair.symbol)
                    bid = tob.best_bid_price
                    ask = tob.best_ask_price
                    if bid and ask:
                        price = (float(bid) + float(ask)) / 2.0
                    else:
                        price = float(bid or ask or 0.0)
                    return pair.symbol, price

            results = await asyncio.gather(*[_fetch_price(p) for p in pairs], return_exceptions=True)
            for item in results:
                if isinstance(item, Exception):
                    continue
                symbol, price = item
                if price and price > 0:
                    triangular.update_price(symbol, price, fee_rate)

            pairs_by_symbol = {p.symbol: p for p in pairs}
            opportunities = []

            for base in base_currencies:
                base_pairs = [p for p in pairs if p.quote == base]
                for p1 in base_pairs:
                    for p2 in base_pairs:
                        if p1.base == p2.base:
                            continue
                        symbol_c = f"{p2.base}/{p1.base}"
                        if symbol_c not in pairs_by_symbol:
                            continue
                        opp = triangular.find_triangular_opportunities(
                            p1.symbol, p2.symbol, symbol_c, float(config.get("initial_amount", 1000.0))
                        )
                        if opp and (opp.expected_profit_rate / 100.0) >= min_profit_rate:
                            opportunities.append(opp)

            if opportunities:
                best = max(opportunities, key=lambda o: o.expected_profit_rate)
                state = self.strategies.get(strategy_id)
                if state:
                    state.total_trades += 1
                    state.total_profit += best.expected_profit
                logger.info(
                    f"三角套利发现机会: exchange={exchange_id} path={best.path} profit={best.expected_profit_rate:.4f}%"
                )
            
        except Exception as e:
            logger.error(f"三角套利执行失败: {e}", exc_info=True)
    
    async def _execute_graph(self, strategy_id: str):
        """图搜索套利策略执行"""
        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                config = await self._get_strategy_config_for_user(conn, strategy_id)
                if not config:
                    return

            cfg_min_profit = float(config.get("min_profit_rate", 0.001))
            cfg_fee_rate = float(config.get("fee_rate", 0.0004))
            exchange_id = str(config.get("exchange_id") or "binance")

            service = await get_config_service()
            pairs = await service.get_pairs_for_exchange(exchange_id)
            if not pairs:
                return

            repo = MarketDataRepository()
            graph = BellmanFordGraph()

            semaphore = asyncio.Semaphore(50)

            async def _fetch_edge(pair):
                async with semaphore:
                    tob = await repo.get_orderbook_tob(exchange_id, pair.symbol)
                    return pair, tob

            results = await asyncio.gather(*[_fetch_edge(p) for p in pairs], return_exceptions=True)
            for item in results:
                if isinstance(item, Exception):
                    continue
                p, tob = item
                if tob.best_bid_price and tob.best_bid_price > 0:
                    rate = float(tob.best_bid_price) * (1 - cfg_fee_rate)
                    if rate > 0:
                        graph.add_edge(p.base, p.quote, -math.log(rate))
                if tob.best_ask_price and tob.best_ask_price > 0:
                    rate = (1.0 / float(tob.best_ask_price)) * (1 - cfg_fee_rate)
                    if rate > 0:
                        graph.add_edge(p.quote, p.base, -math.log(rate))

            cycles = graph.find_negative_cycles()
            if not cycles:
                return

            # 仅选第一个环路计算收益
            cycle = cycles[0]
            if len(cycle) < 2:
                return

            # 计算收益率：exp(-sum(weights)) - 1
            total_weight = 0.0
            for i in range(len(cycle)):
                a = cycle[i]
                b = cycle[(i + 1) % len(cycle)]
                weight = graph.graph.get(a, {}).get(b)
                if weight is None:
                    total_weight = 0.0
                    break
                total_weight += float(weight)
            profit_rate = math.exp(-total_weight) - 1.0 if total_weight else 0.0

            if profit_rate >= cfg_min_profit:
                state = self.strategies.get(strategy_id)
                if state:
                    state.total_trades += 1
                    state.total_profit += profit_rate * 1000.0
                logger.info(f"图搜索套利发现机会: exchange={exchange_id} path={cycle} profit={profit_rate:.4%}")

        except Exception as e:
            logger.error(f"图搜索套利执行失败: {e}", exc_info=True)
    
    async def _execute_funding_rate(self, strategy_id: str):
        """期现套利策略执行"""
        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                config = await self._get_strategy_config_for_user(conn, strategy_id)
                if not config:
                    return

            min_profit_rate = float(config.get("min_profit_rate", 0.001))
            exchange_id = str(config.get("exchange_id") or "binance")

            service = await get_config_service()
            pairs = await service.get_pairs_for_exchange(exchange_id)
            symbols = [p.symbol for p in pairs if p.quote == "USDT"]
            if not symbols:
                return

            repo = MarketDataRepository()
            algo = FundingRateArbitrage()

            semaphore = asyncio.Semaphore(50)

            async def _fetch_symbol(sym: str):
                async with semaphore:
                    spot = await repo.get_best_bid_ask(exchange_id, sym, "spot")
                    perp = await repo.get_best_bid_ask(exchange_id, sym, "perp")
                    funding = await repo.get_funding(exchange_id, sym)
                    return sym, spot, perp, funding

            results = await asyncio.gather(*[_fetch_symbol(s) for s in symbols], return_exceptions=True)
            for item in results:
                if isinstance(item, Exception):
                    continue
                sym, spot, perp, funding = item
                spot_mid = spot.bid or spot.ask or spot.last
                perp_mid = perp.bid or perp.ask or perp.last
                if not spot_mid or not perp_mid:
                    continue
                algo.update_prices(sym, float(spot_mid), float(perp_mid), float(funding.rate or 0.0))

            opportunities = algo.find_opportunities()
            if not opportunities:
                return

            best = max(opportunities, key=lambda o: o.expected_profit_rate)
            if best.expected_profit_rate / 100.0 >= min_profit_rate:
                state = self.strategies.get(strategy_id)
                if state:
                    state.total_trades += 1
                    state.total_profit += best.expected_profit
                logger.info(
                    f"期现套利发现机会: exchange={exchange_id} symbol={best.symbols[0]} profit={best.expected_profit_rate:.4f}%"
                )

        except Exception as e:
            logger.error(f"期现套利执行失败: {e}", exc_info=True)
    
    async def _execute_grid(self, strategy_id: str):
        """网格交易策略执行"""
        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                config = await self._get_strategy_config_for_user(conn, strategy_id)
                if not config:
                    return
            
            from ..exchange.binance_connector import BinanceConnector
            from ..engines.strategies import GridStrategy
            import os
            
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_SECRET_KEY')
            
            if not api_key or not api_secret:
                return
            
            binance = BinanceConnector(api_key, api_secret)
            strategy = GridStrategy(binance, config)
            
            result = await strategy.execute(trading_mode='paper')
            
            if result['success']:
                logger.info(f"网格策略执行成功")
            
            await binance.close()
            
        except Exception as e:
            logger.error(f"网格策略执行失败: {e}")
    
    async def _execute_pair(self, strategy_id: str):
        """配对交易策略执行"""
        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                config = await self._get_strategy_config_for_user(conn, strategy_id)
                if not config:
                    return
            
            from ..exchange.binance_connector import BinanceConnector
            from ..engines.strategies import PairTradingStrategy
            import os
            
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_SECRET_KEY')
            
            if not api_key or not api_secret:
                return
            
            binance = BinanceConnector(api_key, api_secret)
            strategy = PairTradingStrategy(binance, config)
            
            result = await strategy.execute(trading_mode='paper')
            
            if result['success']:
                logger.debug(f"配对交易策略执行成功")
            
            await binance.close()
            
        except Exception as e:
            logger.error(f"配对交易策略执行失败: {e}")

    
    async def stop(self):
        """停止策略引擎"""
        self.is_running = False
        logger.info("正在停止策略引擎...")
        
        # 取消所有运行中的任务
        for task in self._tasks:
            task.cancel()
        
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        
        # 更新数据库中的机器人状态
        await self._update_bot_status('stopped')
        
        logger.info("策略引擎已停止")
    
    async def _update_bot_status(self, status: str):
        """更新数据库中的机器人状态"""
        if not self.user_id:
            return

        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE global_settings
                    SET bot_status = $1, updated_at = NOW()
                    WHERE user_id = $2
                    """,
                    status,
                    self.user_id,
                )
        except Exception as e:
            logger.error(f"更新机器人状态失败: {e}")
    
    # ============================================
    # 状态查询接口
    # ============================================
    
    def get_all_states(self) -> List[Dict]:
        """获取所有策略状态"""
        return [
            {
                'id': state.strategy_id,
                'type': state.strategy_type,
                'name': state.name,
                'isRunning': state.is_running,
                'lastRun': state.last_run.isoformat() if state.last_run else None,
                'totalTrades': state.total_trades,
                'totalProfit': state.total_profit,
                'error': state.error_message
            }
            for state in self.strategies.values()
        ]
    
    def get_state(self, strategy_id: str) -> Optional[Dict]:
        """获取指定策略状态"""
        state = self.strategies.get(strategy_id)
        if not state:
            return None
        return {
            'id': state.strategy_id,
            'type': state.strategy_type,
            'name': state.name,
            'isRunning': state.is_running,
            'lastRun': state.last_run.isoformat() if state.last_run else None,
            'totalTrades': state.total_trades,
            'totalProfit': state.total_profit,
            'error': state.error_message
        }


# ============================================
# 便捷函数
# ============================================

async def get_strategy_engine() -> StrategyEngine:
    """获取策略引擎实例"""
    engine = StrategyEngine.get_instance()
    if not engine.strategies:
        await engine.initialize()
    return engine


async def get_strategy_engine_for_user(user_id: UUID) -> StrategyEngine:
    engine = StrategyEngine.get_instance()
    if engine.user_id != user_id or not engine.strategies:
        await engine.initialize_for_user(user_id)
    return engine


# ============================================
# 策略引擎扩展方法（新增）
# ============================================

async def _get_strategy_scan_interval(self, strategy_id: str) -> float:
    """
    从策略配置中获取扫描间隔
    返回秒数，默认1秒
    """
    now = asyncio.get_event_loop().time()
    cached = self._scan_interval_cache.get(strategy_id)
    if cached and (now - cached[0]) < self._scan_interval_ttl_seconds:
        return cached[1]
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            config = await self._get_strategy_config_for_user(conn, strategy_id)
            if config and 'scan_interval_ms' in config:
                value = config['scan_interval_ms'] / 1000.0
                self._scan_interval_cache[strategy_id] = (now, value)
                return value
    except Exception as e:
        logger.warning(f"无法读取策略扫描间隔: {e}")

    self._scan_interval_cache[strategy_id] = (now, 1.0)
    return 1.0  # 默认1秒


async def _update_strategy_status(self, strategy_id: str, is_enabled: bool, error_msg: str = None):
    """更新数据库中的策略状态"""
    try:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            if error_msg:
                user_id = self.user_id or await conn.fetchval(
                    "SELECT user_id FROM strategy_configs WHERE id = $1",
                    strategy_id,
                )
                # 同时记录到系统日志
                await conn.execute("""
                    INSERT INTO system_logs (user_id, level, source, message, extra)
                    VALUES ($1, 'ERROR', 'strategy_engine', $2, $3::jsonb)
                """, user_id, f"策略自动停止: {error_msg}", {'strategy_id': str(strategy_id)})
            
            if not self.user_id:
                raise ValueError("StrategyEngine user_id is required")

            await conn.execute("""
                UPDATE strategy_configs 
                SET is_enabled = $1, updated_at = NOW()
                WHERE id = $2 AND user_id = $3
            """, is_enabled, strategy_id, self.user_id)
            
    except Exception as e:
        logger.error(f"更新策略状态失败: {e}")


# 将新方法绑定到 StrategyEngine 类
StrategyEngine._get_strategy_scan_interval = _get_strategy_scan_interval
StrategyEngine._update_strategy_status = _update_strategy_status
