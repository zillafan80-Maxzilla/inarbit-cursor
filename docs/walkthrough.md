# Inarbit Walkthrough

本指南用于快速完成一次端到端验证（本地开发环境）。

## 1. 启动依赖

```bash
docker-compose up -d
```

确认 PostgreSQL/Redis 正常运行后继续。

## 2. 启动后端

```bash
uvicorn server.app:app --host 127.0.0.1 --port 8000
```

健康检查：

- `http://127.0.0.1:8000/health`

## 3. 启动前端

```bash
cd client
npm install
npm run dev
```

访问：

- `http://localhost:5173`

默认账号：

- 用户名：admin
- 密码：admin123

## 4. 交易所配置

在前端「交易所管理」页面新增 Binance：

- 粘贴 API Key / Secret
- 勾选现货启用
- 保存

> 若提示 403 或权限不足，请确保密钥开启“Read”权限，并检查 IP 白名单限制。

## 5. 基础验证

- 登录后查看「系统状态 / 监控」
- 检查行情是否刷新
- 验证策略列表可加载

## 6. 模拟盘快速跑盘（可选）

启用三角套利策略并运行 10 秒：

```bash
C:/Users/周浩/VScode-space/inarbit-Vscode/.venv/Scripts/python.exe -c "import asyncio; from server.db import get_pg_pool; from server.engines.strategy_engine import StrategyEngine; async def main():\n    pool = await get_pg_pool();\n    await pool.execute(\"UPDATE strategy_configs SET is_enabled = false\");\n    await pool.execute(\"UPDATE strategy_configs SET is_enabled = true WHERE strategy_type='triangular'\");\n    engine = StrategyEngine.get_instance();\n    await engine.initialize();\n    await engine.start();\n    await asyncio.sleep(10);\n    await engine.stop();\n    print('triangular strategy ran for 10s');\nasyncio.run(main())"
```

## 7. 常见问题

- 后端无法启动：先确认 Docker Desktop 已运行，PostgreSQL/Redis 端口未冲突。
- 登录 403：确认 admin 角色已生效（启动时会自动修复）。
- 行情为空：检查网络或交易所 API 权限与可达性。
