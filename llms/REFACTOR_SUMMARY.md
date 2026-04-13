# LLM 模型参数传递重构总结

## 📋 概述

完成了 Claude 和 Gemini 模型的参数传递重构，确保它们正确接收和处理完整的 API 参数（messages、system、tools 等），并添加了完整的日志系统。

---

## 🔄 主要修改

### 1. Claude 模型 (`claude.py`)

#### 修改前
```python
def generate(
    self,
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.0
) -> Dict[str, Any]:
    # 只支持基本参数
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages
    }
```

#### 修改后
```python
def generate(
    self,
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: Optional[str] = None,  # ✅ 新增
    tools: Optional[List[Dict[str, Any]]] = None  # ✅ 新增
) -> Dict[str, Any]:
    # 支持完整的 Claude API 参数
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages
    }
    
    # 添加可选参数
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools
```

**改进点：**
- ✅ 支持 `system` 参数（系统提示词）
- ✅ 支持 `tools` 参数（工具调用）
- ✅ 完整的错误处理（Timeout, ConnectionError, HTTPError）
- ✅ 详细的日志记录

---

### 2. Claude Provider (`ae_claude_provider.py`)

#### 修改前
```python
def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
    # 使用 to_dict() 方法，可能丢失参数
    messages = question.to_dict()
    
    result = self.claude_model.generate(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0
    )
```

#### 修改后
```python
def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
    # 直接从 question 对象提取所有参数
    messages = question.messages  # ✅ 直接使用 messages
    system = question.system      # ✅ 提取 system
    tools = question.tools        # ✅ 提取 tools
    
    result = self.claude_model.generate(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system,  # ✅ 传递 system
        tools=tools     # ✅ 传递 tools
    )
```

**改进点：**
- ✅ 直接使用 `question.messages` 而不是 `to_dict()`
- ✅ 正确传递 `system` 和 `tools` 参数
- ✅ 完整的日志记录

---

### 3. Gemini 模型 (`gemini_model.py`)

#### 修改前（使用 transformers）
```python
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

def generate(
    self,
    prompt: str,  # ❌ 只支持 prompt
    max_new_tokens: int = 256,
    temperature: float = 0.7,
    top_p: float = 0.9,
    top_k: int = 50,
    do_sample: bool = True
) -> str:
    inputs = self.tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(self.device) for k, v in inputs.items()}
    
    with torch.no_grad():
        outputs = self.model.generate(**inputs, ...)
```

#### 修改后（使用 mlx_lm）
```python
from mlx_lm import load, generate

def generate(
    self,
    messages: List[Dict[str, str]],  # ✅ 支持 messages
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system: Optional[str] = None  # ✅ 支持 system
) -> str:
    # 1. 构建完整的 messages
    formatted_messages = []
    if system:
        formatted_messages.append({
            "role": "system",
            "content": system
        })
    formatted_messages.extend(messages)
    
    # 2. 使用 chat template
    prompt = self.tokenizer.apply_chat_template(
        formatted_messages,
        tokenize=False,
        add_generation_prompt=True
    )
    
    # 3. 调用 mlx_lm 生成
    response = generate(
        self.model,
        self.tokenizer,
        prompt=prompt,
        max_tokens=max_tokens
    )
```

**改进点：**
- ✅ 从 `transformers` 迁移到 `mlx_lm`（更高效）
- ✅ 支持 `messages` 格式（与 Claude 一致）
- ✅ 支持 `system` 参数
- ✅ 使用 `chat_template` 正确格式化消息
- ✅ 完整的日志记录

---

### 4. Gemini Provider (`ae_gemini_provider.py`)

#### 修改前
```python
def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
    # 直接在 provider 中加载 mlx_lm
    from mlx_lm import load, generate
    
    self.gemini_model, self.tokenizer = load(self.model_path)
    
    prompt = self.tokenizer.apply_chat_template(
        question.to_messages(),  # ❌ 方法不存在
        tokenize=False,
        add_generation_prompt=True
    )
```

#### 修改后
```python
def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
    # 使用封装好的 gemini_model
    from llm.gemini.gemini_model import get_gemini_model
    
    self.gemini_model = get_gemini_model()
    self.gemini_model.load()
    
    # 提取参数
    messages = question.messages
    system = question.system
    
    # 调用模型
    response = self.gemini_model.generate(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.7,
        system=system
    )
```

**改进点：**
- ✅ 使用封装的 `gemini_model`，而不是直接使用 `mlx_lm`
- ✅ 正确提取 `messages` 和 `system`
- ✅ 统一的接口和错误处理
- ✅ 完整的日志记录

---

## 📊 参数传递流程

### 完整的数据流

```
用户请求
    ↓
[question.py] 接收请求
    messages: [{"role": "user", "content": "..."}]
    system: "你是一个助手"
    tools: [...]
    ↓
[AEQuestion] 对象封装
    question.messages = messages
    question.system = system
    question.tools = tools
    ↓
[Provider] 提取参数
    messages = question.messages
    system = question.system
    tools = question.tools
    ↓
[Model] 接收完整参数
    - Claude: generate(messages, model, system, tools, ...)
    - Gemini: generate(messages, system, max_tokens, ...)
    ↓
[API] 发送请求
    payload = {
        "messages": messages,
        "system": system,
        "tools": tools,
        ...
    }
```

---

## 🎯 关键改进点

### 1. 统一的接口
所有模型现在都支持：
- `messages`: 标准消息列表格式
- `system`: 系统提示词（可选）
- `tools`: 工具列表（可选，Claude 专用）

### 2. 正确的参数传递
```python
# ❌ 错误方式
messages = question.to_dict()  # 可能丢失结构

# ✅ 正确方式
messages = question.messages   # 直接使用
system = question.system       # 显式提取
tools = question.tools         # 显式提取
```

### 3. 完整的日志记录
每个关键步骤都有日志：
- 🚀 初始化
- 🔄 开始处理
- 📦 参数准备
- 📤 发送请求
- 📥 收到响应
- ✅ 成功
- ❌ 失败

### 4. 错误处理
详细的错误分类：
- `Timeout`: 请求超时
- `ConnectionError`: 连接错误
- `HTTPError`: HTTP 状态码错误
- `Exception`: 其他异常

---

## 📝 使用示例

### Claude 调用示例

```python
from llms.question.AEQuestion import AEQuestion, LLMType, AEAiLevel

# 创建问题对象
question = AEQuestion(
    messages=[
        {"role": "user", "content": "什么是 Python？"}
    ],
    llm_type=LLMType.CLAUDE,
    level=AEAiLevel.high,
    system="你是一个 Python 专家",
    tools=[{
        "name": "get_weather",
        "description": "获取天气信息",
        "parameters": {...}
    }]
)

# 调用 Provider
from llms.llm_providers.ae_claude_provider import AEClaudeProvider

provider = AEClaudeProvider()
response = provider.generate(
    question=question,
    level=AEAiLevel.high,
    max_tokens=4096
)
```

### Gemini 调用示例

```python
from llms.llm.gemini.gemini_model import get_gemini_model

# 获取模型
model = get_gemini_model()
model.load()

# 调用模型
response = model.generate(
    messages=[
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "什么是 Python？"}
    ],
    max_tokens=1024,
    system="你是一个 Python 专家"  # system 也可以单独传递
)
```

---

## 🧪 测试

### 测试文件
- `/Users/tianjunqi/Project/Self/Agents/Service/llms/test_gemini.py` - Gemini 模型测试

### 运行测试
```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/llms
python test_gemini.py
```

---

## 📂 修改的文件

### Claude 相关
1. ✅ `/llms/llm/claude/claude.py`
   - 添加 `system` 和 `tools` 参数支持
   - 添加详细日志
   - 完善错误处理

2. ✅ `/llms/llm_providers/ae_claude_provider.py`
   - 正确提取和传递参数
   - 添加日志记录

### Gemini 相关
3. ✅ `/llms/llm/gemini/gemini_model.py`
   - 从 `transformers` 迁移到 `mlx_lm`
   - 支持 `messages` 和 `system` 参数
   - 添加详细日志

4. ✅ `/llms/llm_providers/ae_gemini_provider.py`
   - 使用封装的 `gemini_model`
   - 正确提取和传递参数
   - 添加日志记录

### 其他
5. ✅ `/llms/routes/question.py`
   - 添加详细的请求日志

6. ✅ `/AEIQ/Context/AEContext.py`
   - 添加完整的日志系统

---

## 🚀 后续工作

### 建议
1. ✅ 测试 Claude API 调用（确保 system 和 tools 参数正常工作）
2. ✅ 测试 Gemini 本地模型（确保 mlx_lm 正常工作）
3. ⏳ 添加更多单元测试
4. ⏳ 性能监控和优化

---

## 📚 相关文档

- [Claude API 文档](https://docs.anthropic.com/claude/reference/messages_post)
- [mlx_lm 文档](https://github.com/ml-explore/mlx-examples/tree/main/llms)
- [LOGGING.md](/Users/tianjunqi/Project/Self/Agents/Service/AEIQ/LOGGING.md) - 日志使用指南
