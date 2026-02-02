"""
邮件简报服务
每日定时发送交易简报到管理员邮箱
"""
import asyncio
import logging
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time
from typing import Optional
from uuid import UUID

from ..db import get_pg_pool, get_redis

logger = logging.getLogger(__name__)


class EmailReportService:
    """邮件简报服务"""
    
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_send_date: Optional[str] = None
    
    async def start(self):
        """启动邮件简报服务"""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("✅ 邮件简报服务已启动")
    
    async def stop(self):
        """停止邮件简报服务"""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except:
                pass
        logger.info("✅ 邮件简报服务已停止")
    
    async def _run(self):
        """定时检查并发送简报"""
        while not self._stop_event.is_set():
            try:
                # 检查是否需要发送简报
                await self._check_and_send()
                
                # 每小时检查一次
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=3600.0)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"邮件简报服务错误: {e}")
                await asyncio.sleep(600)  # 出错后等待10分钟
    
    async def _check_and_send(self):
        """检查是否到达发送时间"""
        pool = await get_pg_pool()
        
        # 获取用户的邮件简报配置
        async with pool.acquire() as conn:
            configs = await conn.fetch("""
                SELECT 
                    u.id as user_id,
                    u.email,
                    u.username,
                    gs.email_report_enabled,
                    gs.email_report_time
                FROM users u
                LEFT JOIN global_settings gs ON gs.user_id = u.id
                WHERE gs.email_report_enabled = true 
                  AND u.email IS NOT NULL
                  AND u.email != ''
            """)
            
            for config in configs:
                await self._send_report_for_user(config)
    
    async def _send_report_for_user(self, user_config):
        """为单个用户发送简报"""
        user_id = user_config['user_id']
        email = user_config['email']
        report_time = user_config['email_report_time'] or '09:00'
        
        # 检查当前时间是否到达发送时间
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        
        # 如果今天已发送过，跳过
        if self._last_send_date == today_str:
            return
        
        # 解析发送时间
        try:
            hour, minute = map(int, report_time.split(':'))
            target_time = time(hour, minute)
            current_time = now.time()
            
            # 如果当前时间在目标时间前1小时内，发送简报
            if current_time.hour == target_time.hour or (
                current_time.hour == target_time.hour - 1 and current_time.minute >= 50
            ):
                # 生成并发送简报
                report_content = await self._generate_report(user_id)
                await self._send_email(email, report_content)
                self._last_send_date = today_str
                logger.info(f"✅ 已发送邮件简报到 {email}")
        except Exception as e:
            logger.error(f"发送邮件简报失败: {e}")
    
    async def _generate_report(self, user_id: UUID) -> str:
        """生成简报内容"""
        pool = await get_pg_pool()
        redis = await get_redis()
        
        async with pool.acquire() as conn:
            # 获取基本信息
            global_config = await conn.fetchrow("""
                SELECT trading_mode, bot_status 
                FROM global_settings 
                WHERE user_id = $1
            """, user_id)
            
            # 获取启用的策略
            strategies = await conn.fetch("""
                SELECT strategy_type, name 
                FROM strategy_configs 
                WHERE user_id = $1 AND is_enabled = true
            """, user_id)
            
            # 获取交易所
            exchanges = await conn.fetch("""
                SELECT exchange_id, display_name 
                FROM exchange_configs 
                WHERE user_id = $1 AND is_active = true
            """, user_id)
            
            # 获取交易对
            pairs = await conn.fetch("""
                SELECT symbol 
                FROM trading_pairs 
                WHERE is_active = true 
                LIMIT 20
            """)
            
            # 获取资金信息
            paper_trading = await conn.fetchrow("""
                SELECT initial_balance, current_balance, realized_pnl
                FROM paper_trading
                WHERE user_id = $1
                ORDER BY created_at DESC LIMIT 1
            """, user_id)
            
            # 获取今日交易统计
            today_orders = await conn.fetchval("""
                SELECT COUNT(*) FROM order_history
                WHERE user_id = $1 
                  AND DATE(created_at) = CURRENT_DATE
            """, user_id)
            
            today_pnl = await conn.fetchval("""
                SELECT COALESCE(SUM(profit), 0) FROM pnl_records
                WHERE user_id = $1 
                  AND DATE(created_at) = CURRENT_DATE
            """, user_id)
        
        # 格式化简报内容
        trading_mode = "模拟盘" if global_config['trading_mode'] == 'paper' else "实盘"
        strategy_list = [f"{s['name']}({s['strategy_type']})" for s in strategies] if strategies else ["无"]
        exchange_list = [e['display_name'] or e['exchange_id'].upper() for e in exchanges] if exchanges else ["无"]
        pair_list = [p['symbol'] for p in pairs[:10]] if pairs else ["无"]
        
        initial = float(paper_trading['initial_balance']) if paper_trading else 0
        current = float(paper_trading['current_balance']) if paper_trading else 0
        net_profit = current - initial
        profit_rate = (net_profit / initial * 100) if initial > 0 else 0
        
        # 生成HTML邮件内容
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #4a5d4a 0%, #2e4a2e 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .stat-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px; background: white; border-radius: 4px; }}
                .stat-label {{ font-weight: bold; color: #4a5d4a; }}
                .stat-value {{ color: #333; }}
                .profit {{ color: {"#00b894" if net_profit >= 0 else "#d63031"}; font-weight: bold; font-size: 1.2em; }}
                .footer {{ text-align: center; padding: 15px; color: #888; font-size: 0.9em; }}
                ul {{ list-style: none; padding: 0; }}
                li {{ padding: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">📊 Inarbit 交易简报</h1>
                    <p style="margin: 5px 0 0 0;">{datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
                </div>
                
                <div class="content">
                    <h2>系统运行状态</h2>
                    <div class="stat-row">
                        <span class="stat-label">运行模式:</span>
                        <span class="stat-value">{"🔴 " if trading_mode == "实盘" else "🟢 "}{trading_mode}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">机器人状态:</span>
                        <span class="stat-value">{global_config['bot_status'] if global_config else '未知'}</span>
                    </div>
                    
                    <h2>交易配置</h2>
                    <div class="stat-row">
                        <span class="stat-label">启用策略:</span>
                        <span class="stat-value">{', '.join(strategy_list)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">连接交易所:</span>
                        <span class="stat-value">{', '.join(exchange_list)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">交易币对:</span>
                        <span class="stat-value">{', '.join(pair_list)}</span>
                    </div>
                    
                    <h2>资金与收益</h2>
                    <div class="stat-row">
                        <span class="stat-label">初始资金:</span>
                        <span class="stat-value">USDT ${initial:,.2f}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">当前资金:</span>
                        <span class="stat-value">USDT ${current:,.2f}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">净利润:</span>
                        <span class="profit">{"+" if net_profit >= 0 else ""}USDT ${net_profit:,.2f} ({profit_rate:+.2f}%)</span>
                    </div>
                    
                    <h2>今日交易</h2>
                    <div class="stat-row">
                        <span class="stat-label">订单数:</span>
                        <span class="stat-value">{today_orders or 0} 笔</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">今日收益:</span>
                        <span class="stat-value">USDT ${float(today_pnl or 0):,.2f}</span>
                    </div>
                    
                    <h2>市场概况</h2>
                    <p>当前市场环境: <strong>正常</strong></p>
                    <p>套利机会: 系统持续扫描中</p>
                    <p>风险状态: 正常监控中</p>
                </div>
                
                <div class="footer">
                    <p>此邮件由 Inarbit 高频交易系统自动发送</p>
                    <p>访问控制面板: <a href="https://inarbit.work">https://inarbit.work</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    async def _send_email(self, to_email: str, html_content: str):
        """发送邮件"""
        # 从环境变量读取SMTP配置
        smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER', '')
        smtp_password = os.getenv('SMTP_PASSWORD', '')
        smtp_from = os.getenv('SMTP_FROM', smtp_user)
        smtp_tls = os.getenv('SMTP_TLS', '0') == '1'
        smtp_ssl = os.getenv('SMTP_SSL', '0') == '1'
        smtp_timeout = int(os.getenv('SMTP_TIMEOUT', '30'))
        
        if not smtp_user or not smtp_password:
            logger.warning("SMTP未配置，跳过发送邮件")
            return
        
        # 创建邮件
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Inarbit 交易简报 - {datetime.now().strftime("%Y-%m-%d")}'
        msg['From'] = smtp_from
        msg['To'] = to_email
        
        # 添加HTML内容
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        # 发送邮件
        try:
            if smtp_ssl:
                # 使用SSL连接（QQ邮箱465端口）
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=smtp_timeout)
            elif smtp_tls:
                # 使用TLS连接（587端口）
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
                server.starttls()
            else:
                # 普通连接
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
            
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"✅ 邮件简报已发送到 {to_email}")
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            raise
    
    async def send_test_email(self, user_id: UUID, to_email: str) -> bool:
        """发送测试邮件"""
        try:
            report_content = await self._generate_report(user_id)
            await self._send_email(to_email, report_content)
            return True
        except Exception as e:
            logger.error(f"发送测试邮件失败: {e}")
            return False


# 全局单例
_email_report_service: Optional[EmailReportService] = None


async def get_email_report_service() -> EmailReportService:
    """获取邮件简报服务实例"""
    global _email_report_service
    if _email_report_service is None:
        _email_report_service = EmailReportService()
    return _email_report_service
