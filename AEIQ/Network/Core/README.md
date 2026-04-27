# 网络数据模型使用文档

## 概述

按照 `AEChatRequest.py` 的设计模式重新实现了 `AENetReq` 和 `AENetRsp`，提供了更加结构化、类型安全的网络数据封装。

## 核心设计理念

### 1. 使用 Enum 定义类型
- `AENetReqAction` - 请求动作枚举
- `AENetRspStatus` - 响应状态枚举

### 2. 嵌套的数据模型
- `AENetReqData` - 请求数据模型
- `AENetRspData` - 响应数据模型
- `AENetErrorInfo` - 错误信息模型

### 3. 使用 Field 进行字段描述
- 提供字段说明文档
- 支持默认值和可选字段

### 4. Pydantic v2 配置
- 使用 `model_config` 替代 `Config` 类
- `use_enum_values = True` 自动转换枚举为值

## API 参考

### AENetReq - 请求模型

#### 请求动作类型 (AENetReqAction)
```python
class AENetReqAction(Enum):
    CHAT = "chat"          # 聊天请求
    QUERY = "query"        # 查询请求
    COMMAND = "command"    # 命令请求
    HEARTBEAT = "heartbeat"  # 心跳
    CLOSE = "close"        # 关闭连接
    CUSTOM = "custom"      # 自定义动作
```

#### 创建请求
```python
from AEIQ.Network.Core import AENetReq, AENetReqAction, AENetReqData

# 方式1: 使用枚举
req = AENetReq(
    action=AENetReqAction.CHAT,
    data=AENetReqData(
        content="用户输入的内容",
        parameters={"key": "value"}
    ),
    request_id="req_001"
)

# 方式2: 从 JSON 字符串
json_str = '{"action": "query", "data": null, "request_id": "req_002"}'
req = AENetReq.model_validate_json(json_str)

# 方式3: 从字典
req_dict = {"action": "command", "data": {"content": "ls -la"}}
req = AENetReq.model_validate(req_dict)
```

#### 序列化和反序列化
```python
# 序列化为字节流（带长度前缀）
bytes_data = req.to_bytes()

# 反序列化（跳过前4字节的长度标记）
req_restored = AENetReq.from_bytes(bytes_data[4:])
```

### AENetRsp - 响应模型

#### 响应状态类型 (AENetRspStatus)
```python
class AENetRspStatus(Enum):
    SUCCESS = "success"          # 成功
    ERROR = "error"              # 错误
    TIMEOUT = "timeout"          # 超时
    INVALID = "invalid"          # 无效请求
    UNAUTHORIZED = "unauthorized"  # 未授权
    PROCESSING = "processing"    # 处理中
```

#### 创建成功响应
```python
from AEIQ.Network.Core import AENetRsp, AENetRspData

# 方式1: 使用构造函数
rsp = AENetRsp(
    status=AENetRspStatus.SUCCESS,
    data=AENetRspData(
        content="处理成功",
        result={"count": 100}
    ),
    request_id="req_001"
)

# 方式2: 使用快捷方法（推荐）
rsp = AENetRsp.create_success(
    data=AENetRspData(
        content="处理成功",
        result={"count": 100}
    ),
    request_id="req_001"
)
```

#### 创建错误响应
```python
from AEIQ.Network.Core import AENetRsp, AENetErrorInfo

# 方式1: 使用构造函数
rsp = AENetRsp(
    status=AENetRspStatus.ERROR,
    error=AENetErrorInfo(
        code="ERR_DB_001",
        message="数据库连接失败",
        details={"host": "localhost"}
    ),
    request_id="req_001"
)

# 方式2: 使用快捷方法（推荐）
rsp = AENetRsp.create_error(
    error_code="ERR_DB_001",
    error_message="数据库连接失败",
    error_details={"host": "localhost"},
    request_id="req_001"
)
```

#### 检查响应状态
```python
# 检查是否成功
if rsp.is_success:
    print("处理成功")
    print(f"结果: {rsp.data.result}")

# 检查是否错误
if rsp.is_error:
    print(f"错误: {rsp.error.code} - {rsp.error.message}")
```

## 完整使用示例

### 客户端发送请求
```python
from AEIQ.Network.Core import AENetReq, AENetReqAction, AENetReqData
from AEIQ.Network.Socket import AESocketWrapper

# 1. 创建请求
request = AENetReq(
    action=AENetReqAction.CHAT,
    data=AENetReqData(
        content="你好，请帮我查询天气",
        parameters={"location": "北京"}
    ),
    request_id="req_001"
)

# 2. 发送请求
wrapper.send(request)
```

### 服务端处理请求并响应
```python
from AEIQ.Network.Core import AENetRsp, AENetRspData
from AEIQ.Network.Socket import AESocketListener

class MyListener(AESocketListener):
    def on_data_received(self, data):
        # 注意：这里接收到的是 AENetRsp 格式
        # 如果需要接收 AENetReq，需要相应调整 Socket 包装器
        
        try:
            # 处理请求
            result = process_request(data)
            
            # 创建成功响应
            response = AENetRsp.create_success(
                data=AENetRspData(
                    content="处理成功",
                    result=result
                ),
                request_id=data.request_id
            )
        except Exception as e:
            # 创建错误响应
            response = AENetRsp.create_error(
                error_code="ERR_500",
                error_message=str(e),
                request_id=data.request_id
            )
        
        # 发送响应
        self.wrapper.send(response)
```

## 数据格式

### 请求 JSON 格式
```json
{
  "action": "chat",
  "data": {
    "content": "用户输入的内容",
    "parameters": {
      "key": "value"
    }
  },
  "request_id": "req_001"
}
```

### 成功响应 JSON 格式
```json
{
  "status": "success",
  "data": {
    "content": "响应内容",
    "result": {
      "key": "value"
    }
  },
  "error": null,
  "request_id": "req_001"
}
```

### 错误响应 JSON 格式
```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "ERR_001",
    "message": "错误消息",
    "details": {
      "reason": "详细原因"
    }
  },
  "request_id": "req_001"
}
```

## 与 AEChatRequest 的对比

### 相同之处
1. ✅ 使用 Enum 定义类型
2. ✅ 嵌套的数据模型结构
3. ✅ 使用 Field 提供字段描述
4. ✅ 使用 `use_enum_values = True` 自动转换枚举
5. ✅ 清晰的文档注释和示例

### 特色功能
1. ✅ 提供快捷方法（`create_success`, `create_error`）
2. ✅ 提供属性方法（`is_success`, `is_error`）
3. ✅ 支持多种状态类型（success, error, timeout, processing 等）
4. ✅ 结构化的错误信息（code, message, details）
5. ✅ 序列化/反序列化方法（`to_bytes`, `from_bytes`）

## 最佳实践

### 1. 使用枚举而非字符串
```python
# ✅ 推荐
req = AENetReq(action=AENetReqAction.CHAT)

# ❌ 不推荐（虽然也能工作）
req_dict = {"action": "chat"}
req = AENetReq.model_validate(req_dict)
```

### 2. 使用快捷方法创建响应
```python
# ✅ 推荐 - 简洁明了
rsp = AENetRsp.create_success(data=data)

# ❌ 不推荐 - 冗长
rsp = AENetRsp(status=AENetRspStatus.SUCCESS, data=data)
```

### 3. 使用属性方法检查状态
```python
# ✅ 推荐 - 语义清晰
if rsp.is_success:
    ...

# ❌ 不推荐 - 需要记住枚举值
if rsp.status == "success":
    ...
```

### 4. 结构化错误信息
```python
# ✅ 推荐 - 完整的错误信息
rsp = AENetRsp.create_error(
    error_code="ERR_DB_001",
    error_message="数据库连接失败",
    error_details={"host": "localhost", "port": 5432}
)

# ❌ 不推荐 - 信息不足
rsp = AENetRsp.create_error(
    error_code="ERROR",
    error_message="失败"
)
```

## 运行示例和测试

### 运行示例代码
```bash
python -m AEIQ.Network.Core.example_usage
```

### 运行单元测试
```bash
python -m unittest AEIQ.Network.Core.test_models -v
```

## 迁移指南

### 从旧版本迁移

如果你之前使用的是简单版本的 AENetReq/AENetRsp：

#### 请求部分
```python
# 旧版本
req = AENetReq(
    action="chat",
    data={"content": "hello", "params": {...}}
)

# 新版本
req = AENetReq(
    action=AENetReqAction.CHAT,
    data=AENetReqData(
        content="hello",
        parameters={...}
    )
)
```

#### 响应部分
```python
# 旧版本
rsp = AENetRsp(
    success=True,
    data={"result": "ok"},
    error=None
)

# 新版本
rsp = AENetRsp.create_success(
    data=AENetRspData(
        content="ok",
        result={...}
    )
)
```

## 类型提示支持

所有类都是完全类型化的，支持 IDE 智能提示：

```python
def handle_request(req: AENetReq) -> AENetRsp:
    """处理请求并返回响应"""
    # IDE 会提供完整的类型提示
    action: str = req.action
    data: Optional[AENetReqData] = req.data
    
    if req.action == AENetReqAction.CHAT.value:
        # 处理聊天请求
        pass
    
    return AENetRsp.create_success(...)
```

## 总结

新的数据模型设计：
- ✅ 更加规范和结构化
- ✅ 类型安全，减少错误
- ✅ 易于扩展和维护
- ✅ 提供清晰的 API 和文档
- ✅ 完全兼容 Pydantic v2
- ✅ 遵循 AEChatRequest 的设计模式
