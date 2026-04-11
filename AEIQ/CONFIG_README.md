# AEIQ 配置说明

## 统一配置文件

AEIQ 工程使用 **`AEIQConfig.py`** 作为唯一的配置文件，所有组件都从这个文件读取配置。

### 配置文件位置

```
/Users/tianjunqi/Project/Self/Agents/Service/AEIQ/AEIQConfig.py
```

### 配置项说明

```python
class AEIQConfig:
    # LLM 服务配置
    LLM_SERVICE_URL = "http://localhost:9999"  # LLM 服务地址（固定）
    LLM_SERVICE_TIMEOUT = 60                    # HTTP 请求超时时间（秒）

    # 会话管理配置
    SESSION_TIMEOUT = 3600                      # 会话超时时间（秒），默认 1 小时

    # 线程池配置
    EXECUTOR_MAX_WORKERS = 4                    # 并发调用 LLM 的最大线程数

    # FastAPI 配置
    APP_TITLE = "AEIQ API"
    APP_DESCRIPTION = "AI Agent with Multi-LLM Support via HTTP"
    APP_VERSION = "3.0.0"
    AEIQ_PORT = 8000                           # AEIQ 服务端口
```

## 使用配置的组件

### 1. AEContext

```python
from AEIQConfig import config

context = AEContext(session_id="test")
# 自动使用 config.LLM_SERVICE_URL
# 自动使用 config.EXECUTOR_MAX_WORKERS
```

### 2. AEContextManager

```python
manager = AEContextManager()
# 自动使用 config.SESSION_TIMEOUT
```

### 3. app.py

```python
from AEIQConfig import config

app = FastAPI(
    title=config.APP_TITLE,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION
)
```

## 修改配置

### 方法 1: 直接修改配置文件（推荐）

编辑 `AEIQConfig.py`：

```python
class AEIQConfig:
    LLM_SERVICE_URL = "http://192.168.1.100:9999"  # 修改为远程地址
    EXECUTOR_MAX_WORKERS = 8                       # 增加并发数
```

### 方法 2: 使用环境变量

```bash
export LLM_SERVICE_URL="http://remote-server:9999"
python -m uvicorn app:app --port 8000
```

配置文件中支持环境变量覆盖：

```python
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:9999")
```

## 测试配置

运行配置测试脚本：

```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/AEIQ
python test_config.py
```

输出示例：

```
✅ LLM 服务地址: http://localhost:9999
✅ 请求超时时间: 60 秒
✅ 会话超时时间: 3600 秒
✅ 线程池大小: 4
✅ 应用标题: AEIQ API
✅ 应用版本: 3.0.0
```

## 配置优势

1. **集中管理**: 所有配置在一个文件中，易于维护
2. **类型安全**: 使用类属性，有 IDE 提示
3. **环境变量支持**: 可以在不同环境使用不同配置
4. **统一访问**: 通过 `config.get_xxx()` 方法访问
5. **易于扩展**: 添加新配置只需在 AEIQConfig 类中添加

## 配置项详细说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LLM_SERVICE_URL` | `http://localhost:9999` | LLM 服务的 HTTP 地址 |
| `LLM_SERVICE_TIMEOUT` | `60` | HTTP 请求超时时间（秒） |
| `SESSION_TIMEOUT` | `3600` | 会话空闲超时时间（秒） |
| `EXECUTOR_MAX_WORKERS` | `4` | 并发调用 LLM 的最大线程数 |
| `APP_TITLE` | `AEIQ API` | FastAPI 应用标题 |
| `APP_DESCRIPTION` | `AI Agent with...` | FastAPI 应用描述 |
| `APP_VERSION` | `3.0.0` | FastAPI 应用版本 |
| `AEIQ_PORT` | `8000` | AEIQ 服务监听端口 |

## 常见问题

### Q: 如何修改 LLM 服务地址？

A: 修改 `AEIQConfig.py` 中的 `LLM_SERVICE_URL`：

```python
LLM_SERVICE_URL = "http://192.168.1.100:9999"
```

### Q: 配置修改后需要重启服务吗？

A: 是的，修改配置后需要重启 AEIQ 服务才能生效。

### Q: 可以为不同环境使用不同配置吗？

A: 可以，使用环境变量：

```bash
# 开发环境
export LLM_SERVICE_URL="http://localhost:9999"

# 生产环境
export LLM_SERVICE_URL="http://prod-llm-server:9999"
```

### Q: 如何增加并发处理能力？

A: 修改 `EXECUTOR_MAX_WORKERS`：

```python
EXECUTOR_MAX_WORKERS = 8  # 从 4 增加到 8
```

## 配置验证

启动服务时会显示当前配置：

```bash
uvicorn app:app --port 8000

INFO:     Started server process [12345]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

访问 `/docs` 查看 API 文档，标题和版本号来自配置文件。
