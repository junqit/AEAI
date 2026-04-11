# AI Agent 架构

一个基于 Agent、Router、Skill、MCP、RAG 的动态 AI 系统。

## 架构特点

- **动态化**: 工具发现、参数生成、策略选择完全动态
- **解耦**: Agent、Router、Skill、MCP 层次分明
- **可扩展**: 新增工具或策略无需修改核心代码
- **可观测**: 完整的执行链路追踪

## 目录结构

```
Agents/
├── agent_one/           # Agent 层
│   ├── app.py          # 原始应用（保留）
│   ├── app_new.py      # 新架构应用 ⭐
│   ├── task.py         # 任务定义 ⭐
│   ├── context.py      # 上下文管理 ⭐
│   ├── orchestrator.py # 编排器 ⭐
│   └── tools.py        # 工具定义
├── router/             # Router 层
│   ├── router.py       # 主路由器 ⭐
│   └── strategy.py     # 策略定义 ⭐
├── skills/             # Skill 层
│   ├── base_skill.py   # 基类 ⭐
│   ├── mcp_skill.py    # MCP 技能 ⭐
│   ├── rag_skill.py    # RAG 技能 ⭐
│   ├── llm_skill.py    # LLM 技能 ⭐
│   └── hybrid_skill.py # 混合技能 ⭐
├── mcp/                # MCP 层
│   ├── mcp_server.py   # MCP 服务器
│   └── tools/          # 工具实现（待扩展）
├── rag/                # RAG 层
│   └── aerag.py        # RAG 控制器
├── llms/               # LLM 层
│   ├── AEAiLevel.py    # 模型级别
│   ├── claude/         # Claude 实现
│   └── ruleRouter.py   # 旧路由（向后兼容）
├── ARCHITECTURE.md     # 架构设计文档 ⭐
├── test_architecture.py# 测试脚本 ⭐
└── README.md          # 本文件 ⭐
```

⭐ 表示新架构核心文件

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn anthropic sentence-transformers
```

### 2. 运行测试

```bash
python test_architecture.py
```

输出示例：
```
🚀 开始架构测试
=========================================
  测试 1: MCP Skill - 计算任务
=========================================

用户查询: 123 + 456 等于多少？

✓ 成功: True
✓ 策略: mcp
✓ 回答: 579
```

### 3. 启动 API 服务

```bash
python agent_one/app_new.py
```

访问 http://localhost:8000/docs 查看 API 文档。

### 4. API 使用示例

#### 聊天接口

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "123 + 456 等于多少？",
    "session_id": "test-session-1"
  }'
```

响应：
```json
{
  "success": true,
  "response": "579",
  "strategy": "mcp",
  "task_id": "20260329123456789",
  "session_id": "test-session-1"
}
```

#### 解释路由决策

```bash
curl -X POST "http://localhost:8000/explain" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "123 + 456"
  }'
```

#### 列出可用工具

```bash
curl "http://localhost:8000/tools"
```

#### 列出技能信息

```bash
curl "http://localhost:8000/skills"
```

## 核心概念

### 1. Task（任务）

任务是 Agent 的基本处理单元，包含：
- **query**: 用户查询
- **task_type**: 任务类型
- **strategy**: 执行策略（由 Router 决定）
- **params**: 任务参数
- **result**: 执行结果
- **execution_history**: 执行历史

```python
from agent_one.task import Task

task = Task.from_query("123 + 456")
```

### 2. Context（上下文）

管理对话上下文、历史消息、工具调用记录：

```python
from agent_one.context import Context

context = Context()
context.add_user_message("Hello")
context.add_assistant_message("Hi!")
```

### 3. Router（路由器）

多级路由策略：
1. **规则路由**: 基于模式匹配（快速、确定性强）
2. **向量路由**: 基于语义相似度（灵活、需要模型）
3. **LLM 路由**: LLM 兜底（最灵活、但较慢）

```python
from router.router import Router

router = Router()
strategy = router.route("123 + 456")
# strategy.type = "mcp"
```

### 4. Skill（技能）

四种核心技能：

#### MCP Skill - 工具调用
```python
from skills.mcp_skill import MCPSkill

skill = MCPSkill()
result = await skill.execute(task, context)
```

#### RAG Skill - 知识检索
```python
from skills.rag_skill import RAGSkill

skill = RAGSkill(top_k=5, threshold=0.7)
result = await skill.execute(task, context)
```

#### LLM Skill - 直接生成
```python
from skills.llm_skill import LLMSkill

skill = LLMSkill()
result = await skill.execute(task, context)
```

#### Hybrid Skill - 混合策略
```python
from skills.hybrid_skill import HybridSkill

skill = HybridSkill()
result = await skill.execute(task, context)
```

### 5. Orchestrator（编排器）

协调所有组件的核心：

```python
from agent_one.orchestrator import get_orchestrator

orchestrator = get_orchestrator()

# 简单使用
result = orchestrator.process_query("123 + 456")

# 完整使用
task = Task.from_query("123 + 456")
context = Context()
result = orchestrator.execute_task_sync(task, context)
```

## 数据流示例

### 场景1: 计算任务

```
用户: "123 + 456"
  ↓
Orchestrator: 创建 Task
  ↓
Router: rule_route() → "mcp"
  ↓
MCPSkill:
  - 发现工具: "add"
  - 生成参数: {a: 123, b: 456}
  - 执行: add(123, 456)
  - 结果: {"result": 579}
  ↓
Orchestrator: 返回 "579"
```

### 场景2: 知识问答

```
用户: "什么是 MCP？"
  ↓
Orchestrator: 创建 Task
  ↓
Router: rule_route() → "rag"
  ↓
RAGSkill:
  - 检索: top_k=5 相关文档
  - 构造增强提示词
  - LLM 生成回答
  ↓
Orchestrator: 返回回答
```

## 扩展指南

### 添加新工具

1. 在 `agent_one/tools.py` 中注册工具：

```python
def my_new_tool(param1: str, param2: int):
    # 工具逻辑
    return {"result": "..."}

TOOLS["my_new_tool"] = {
    "func": my_new_tool,
    "schema": {
        "name": "my_new_tool",
        "description": "工具描述",
        "input_schema": {
            "type": "object",
            "properties": {
                "param1": {"type": "string"},
                "param2": {"type": "integer"}
            },
            "required": ["param1", "param2"]
        }
    }
}
```

2. 无需修改其他代码，工具会自动被发现和使用！

### 添加新路由规则

在 `router/router.py` 的 `_init_rules()` 中添加：

```python
self.my_patterns = [
    r'关键词1',
    r'关键词2'
]
```

然后在 `_rule_route()` 中添加判断逻辑。

### 添加新技能

1. 继承 `BaseSkill`
2. 实现 `execute()` 和 `can_handle()`
3. 在 `Orchestrator` 中注册

```python
from skills.base_skill import BaseSkill

class MySkill(BaseSkill):
    def __init__(self):
        super().__init__("My Skill", "My skill description")

    async def execute(self, task, context):
        # 实现逻辑
        return self.create_result(success=True, data="...")

    def can_handle(self, task):
        return task.strategy == "my_strategy"
```

## 性能优化

1. **缓存**: Router 可以缓存路由决策
2. **并行**: Hybrid Skill 可以并行执行独立步骤
3. **流式**: LLM Skill 支持流式生成（待实现）
4. **批处理**: MCP 工具支持批量调用（待实现）

## 监控和调试

### 查看执行历史

```python
result = orchestrator.process_query("...")
print(result['execution_history'])
```

### 查看路由决策

```python
explanation = orchestrator.explain_decision("...")
print(explanation)
```

### 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 常见问题

### Q: 如何切换模型？

A: 修改 `llms/claude/claude.py` 中的模型配置，或者在 Skill 初始化时指定：

```python
from llms.AEAiLevel import AEAiLevel
skill = LLMSkill(model_level=AEAiLevel.high)
```

### Q: 如何持久化对话？

A: 使用 Context 的保存和加载方法：

```python
context.save_to_file("session.json")
context = Context.load_from_file("session.json")
```

### Q: 如何集成真实的 MCP 服务器？

A: 修改 `mcp/app.py` 和 `MCPSkill` 使用 MCP 协议连接远程服务器。

### Q: 如何添加 RAG 知识库？

A: 完善 `rag/aerag.py`，实现 FAISS 向量存储和文档索引。

## 下一步计划

- [ ] 完善 MCP 工具注册机制
- [ ] 实现 FAISS 向量存储
- [ ] 添加更多工具（文件操作、API 调用等）
- [ ] 实现流式生成
- [ ] 添加认证和权限控制
- [ ] 性能优化和缓存
- [ ] 完善监控和日志
- [ ] 支持插件系统

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可

MIT License
