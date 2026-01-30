# Inarbit 高频交易系统快速启动指南

## 🚀 快速开始

### 1. 启动数据库服务

```bash
# 在项目根目录
docker-compose up -d
```

等待几秒确保数据库启动完成。

### 2. 安装Python依赖

```bash
# 创建虚拟环境（可选但推荐）
python -m venv venv

# Windows激活
venv\Scripts\activate

# Linux/Mac激活
source venv/bin/activate

# 安装依赖
cd server
pip install -r requirements.txt
```

### 3. 运行系统初始化脚本

```bash
# 返回项目根目录
cd ..

# 运行初始化（会提示输入YES确认重置）
python test_system_init.py
```

### 4. 启动后端服务

```bash
# 方法1：开发模式（推荐）
cd server
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 方法2：使用启动脚本
python start_server.py
```

### 5. 启动前端服务

打开**新的终端窗口**：

```bash
cd client
npm install   # 首次运行需要
npm run dev
```

### 6. 访问系统

打开浏览器访问：

- **前端界面**: <http://localhost:5173>
- **API文档**: <http://localhost:8000/api/docs>
- **系统指标**: <http://localhost:8000/api/v1/system/metrics>

### 7. 登录系统

- 用户名: `admin`
- 密码: `admin123`

## ⚠️ 重要提示

1. **模拟模式**: 当前系统处于模拟盘模式，不会执行真实交易
2. **API密钥**: 已配置真实Binance API密钥，但仅用于获取行情数据
3. **数据重置**: 初始化脚本会清空所有数据，请谨慎使用
4. **风控与OMS**: 可通过环境变量启用风控检查与OMS幂等/轮询策略（见 server/.env.example）
5. **OMS订单流**: 可通过 `OMS_PUBLISH_ORDER_DETAIL=1` 在订单状态推送中附带订单详情（plan_id/symbol/side 等）

## 📝 验证清单

- [ ] Docker容器运行中 (`docker ps`)
- [ ] Python依赖已安装
- [ ] 初始化脚本运行成功
- [ ] 后端服务启动 (8000端口)
- [ ] 前端服务启动 (5173端口)
- [ ] 能够访问管理界面
- [ ] 能够登录admin账户

## 🐛 常见问题

**Q: Docker启动失败**

```bash
# 检查端口占用
netstat -ano | findstr "5432"
netstat -ano | findstr "6379"

# 重启Docker
docker-compose down
docker-compose up -d
```

**Q: Python依赖安装失败**

```bash
# 升级pip
python -m pip install --upgrade pip

# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Q: 前端npm install失败**

```bash
# 清除缓存
npm cache clean --force

# 使用淘宝镜像
npm install --registry=https://registry.npmmirror.com
```

## 📊 测试系统功能

### 测试策略执行

1. 访问「策略管理」页面
2. 找到「三角套利」策略
3. 点击「启动」按钮
4. 查看「运行日志」页面

### 查看实时数据

1. 访问「实时价格」页面
2. 查看BTC/USDT等主流币种价格
3. 检查数据是否实时更新

### 检查模拟盘

1. 访问「模拟配置」页面
2. 确认初始资金为1000 USDT
3. 查看当前余额和收益

## 🎉 完成

系统已就绪，可以开始测试和使用！
