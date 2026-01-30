# 机会配置 API 示例

## 获取单个配置

```
GET /api/v1/config/opportunity/graph
```

响应示例：
```json
{
  "success": true,
  "data": {
    "strategyType": "graph",
    "config": {
      "min_profit_rate": 0.002,
      "max_path_length": 5
    },
    "version": 2,
    "updatedAt": "2026-01-30T12:00:00+08:00"
  }
}
```

## 更新配置

```
PUT /api/v1/config/opportunity/grid
Content-Type: application/json
```

请求体示例：
```json
{
  "config": {
    "grids": [
      {
        "symbol": "BTC/USDT",
        "upper_price": 80000,
        "lower_price": 60000,
        "grid_count": 20
      }
    ]
  }
}
```

响应示例：
```json
{
  "success": true,
  "data": {
    "strategyType": "grid",
    "config": {
      "grids": [
        {
          "symbol": "BTC/USDT",
          "upper_price": 80000,
          "lower_price": 60000,
          "grid_count": 20
        }
      ]
    },
    "version": 3,
    "updatedAt": "2026-01-30T12:05:00+08:00"
  }
}
```

## 获取全部机会配置

```
GET /api/v1/config/opportunity
```
