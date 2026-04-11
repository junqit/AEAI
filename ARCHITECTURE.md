# 正确的服务架构

## 🏗️ 架构说明

```
┌─────────────────────────────────────────────────┐
│                  Agent 服务器                    │
│         /Users/.../Service/agent                │
│                                                  │
│  • FastAPI App (端口: 8000)                      │
│  • Router, Skills, MCP, RAG                     │
│  • Context 管理                                  │
│                                                  │
│            通过 HTTP 调用 ↓                       │
└─────────────────────────────────────────────────┘
                        │
                        │ HTTP POST
                        │
┌─────────────────────────────────────────────────┐
│                   LLM 服务器                     │
│         /Users/.../Service/llms                 │
│                                                  │
│  • FastAPI App (端口: 8001)                      │
│  • AELlmManager (统一管理)                       │
│  • Provider 架构                                 │
│    - AEClaudeProvider                           │
│    - AEChatGPTProvider                          │
│    - AEDeepSeekProvider                         │
│    - AEGeminiProvider                           │
│                                                  │
│            分发到各 LLM API ↓                    │
└─────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
    Claude API    ChatGPT API    Gemini Local
```

## ❌ 当前问题

**Agent 服务器 (`agent/app.py`)**:
```python
# ❌ 错误：直接导入 LLM 模块
from llms.AELlmManager import AELlmManager
llm_manager = AELlmManager()
```

**问题**：
- Agent 和 LLM 服务器耦合
- 无法独立部署
- 无法独立扩展

## ✅ 正确架构

### 1. LLM 服务器 (`llms/`)

**职责**：
- 提供统一的 LLM HTTP API
- 管理所有 LLM Provider
- 处理 LLM 请求的分发

**端口**: 8001

**API 接口**：
```
POST /message
POST /chat
GET /llm/status
GET /health
```

### 2. Agent 服务器 (`agent/`)

**职责**：
- Agent 业务逻辑
- Router, Skills, MCP, RAG
- Context 管理

**端口**: 8000

**LLM 调用方式**：
```python
# ✅ 正确：通过 HTTP 调用 LLM 服务器
import requests

response = requests.post(
    "http://localhost:8001/message",
    json={
        "message": "你好",
        "llm_type": "claude",
        "level": "default"
    }
)
```

## 📝 需要修改的文件

### 1. Agent 服务器修改

**文件**: `agent/app.py`

```python
# ❌ 删除这些
from llms.AELlmManager import AELlmManager
llm_manager = AELlmManager()

# ✅ 改为配置 LLM 服务器地址
import os
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:8001")
```

**创建**: `agent/llm_client.py`

```python
"""
LLM 客户端 - 通过 HTTP 调用 LLM 服务器
"""
import requests
from typing import Optional, Dict, Any

class AELlmClient:
    """LLM 服务客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.timeout = 60
    
    def generate(
        self,
        message: str,
        llm_type: Optional[str] = None,
        level: str = "default",
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 256
    ) -> str:
        """
        调用 LLM 服务生成响应
        
        Args:
            message: 用户消息
            llm_type: LLM 类型 (claude/chatgpt/deepseek/gemini)
            level: AI 级别 (default/middle/high)
            context: 上下文
            max_tokens: 最大 token 数
            
        Returns:
            str: LLM 生成的响应
        """
        payload = {
            "message": message,
            "level": level,
            "context": context or {}
        }
        
        if llm_type:
            payload["llm_type"] = llm_type
        
        if max_tokens:
            payload["context"]["max_tokens"] = max_tokens
        
        response = requests.post(
            f"{self.base_url}/message",
            json=payload,
            timeout=self.timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"LLM 服务调用失败: {response.status_code}")
        
        result = response.json()
        return result.get("response", "")
    
    def health_check(self) -> bool:
        """检查 LLM 服务是否可用"""
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
```

### 2. LLM 服务器配置

**文件**: `llms/app.py`

**修改端口**：
```python
# 确保 LLM 服务器使用不同端口
uvicorn.run(
    "app:app",
    host="0.0.0.0",
    port=8001,  # LLM 服务器端口
    reload=True
)
```

**或通过配置**：
```python
# llms/config.py
HOST = "0.0.0.0"
PORT = 8001  # LLM 服务器端口
```

## 🚀 启动顺序

### 1. 启动 LLM 服务器
```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/llms
python app.py

# 或
DEFAULT_LLM_TYPE=claude python app.py
```

**访问**: http://localhost:8001

### 2. 启动 Agent 服务器
```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/agent
python app.py
```

**访问**: http://localhost:8000

## 📊 请求流程

```
用户请求
    ↓
Agent 服务器 (localhost:8000)
    ↓ HTTP POST
LLM 服务器 (localhost:8001)
    ↓
AELlmManager
    ↓
AEClaudeProvider
    ↓
Claude API
    ↓
返回响应
```

## 🔧 环境变量配置

### Agent 服务器 (`.env`)
```bash
# Agent 服务配置
HOST=0.0.0.0
PORT=8000

# LLM 服务地址
LLM_SERVICE_URL=http://localhost:8001
```

### LLM 服务器 (`.env`)
```bash
# LLM 服务配置
HOST=0.0.0.0
PORT=8001

# 默认 LLM 类型
DEFAULT_LLM_TYPE=claude
```

## ✅ 优势

1. **解耦**: Agent 和 LLM 服务独立
2. **可扩展**: LLM 服务可独立扩展
3. **可维护**: 各自独立维护
4. **灵活部署**: 可部署在不同机器
5. **容错**: Agent 服务不受 LLM 服务影响

## 📝 下一步工作

1. ✅ LLM 服务器已完成（使用 AELlmManager）
2. ⏳ 创建 `agent/llm_client.py`
3. ⏳ 修改 `agent/app.py` 使用 HTTP 客户端
4. ⏳ 更新 Agent 路由使用 LLM 客户端
5. ⏳ 配置不同端口
6. ⏳ 测试服务间调用

---

**重要**: Agent 服务器不应该直接导入 `llms` 模块，应该通过 HTTP 调用！
