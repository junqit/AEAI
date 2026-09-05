# Provider 异步并发控制设计

## 背景与目标

当前 `llms/routes/question.py` 用全局 `ThreadPoolExecutor(max_workers=10)` 给**所有** LLM provider 共用，并发控制与 route 耦合，且所有 provider 共享同一上限。问题：

- 无法 per-provider 区分并发上限——qwen 本地模型（`10.220.146.132:10000`）应串行（GPU 推理能力有限），claude/gemini 等云端 API 可高并发。
- 并发职责错放 route 层，provider 自身无法管控对自身后端的并发压力。

**目标**：把并发控制下移到 provider 层，per-provider 各自管理并发上限；route 不再控制并行。

## 架构

### 调用链

```
route process_question (async)
  └─ await manager.generate (async)
       └─ await provider.generate (async)            # AEBaseProvider 基类
            ├─ async with self._semaphore             # per-provider 并发闸
            └─ await asyncio.to_thread(_generate)     # 同步 _generate 入线程池，不阻塞事件循环
                 └─ _generate (sync, 各子类不变)
                      └─ model.generate (sync, requests.post)
```

### 组件变更

**`AEBaseProvider`（`ae_base_provider.py`）——核心**
- `generate` 改为 `async def generate(...)`：保留现有 messages/result 日志；执行体 `async with self._semaphore: return await asyncio.to_thread(self._generate, question, think_process, delta_process)`。
- 新增类属性 `MAX_CONCURRENCY: int = 10`（默认）与 `CONCURRENCY_ENV_KEY: Optional[str] = None`（环境变量名，`None` 表示不读环境变量）。
- `__init__` 初始化 `self._semaphore: Optional[asyncio.Semaphore] = None`。
- 新增 `_get_semaphore()` lazy 创建：首次 async 调用时按 `MAX_CONCURRENCY`（若 `CONCURRENCY_ENV_KEY` 环境变量存在且为正整数则覆盖）创建 `asyncio.Semaphore`。lazy 创建是为兼容 Python 3.9 的 `Semaphore` 事件循环绑定行为（3.9 中无 running loop 时构造会绑定 loop，3.10+ 才解绑）。
- `_generate` 抽象方法签名不变（各子类同步实现不动）。

**各 provider 子类**
- `AEQwenProvider`：`MAX_CONCURRENCY = 1`，`CONCURRENCY_ENV_KEY = "QWEN_MAX_CONCURRENCY"`。
- `AEClaudeProvider` / `AEGeminiProvider` / `AEDeepSeekProvider` / `AEZhipuProvider` / `AEChatgptProvider`：`MAX_CONCURRENCY = 10`，各自 `CONCURRENCY_ENV_KEY`（`CLAUDE_MAX_CONCURRENCY` / `GEMINI_MAX_CONCURRENCY` / `DEEPSEEK_MAX_CONCURRENCY` / `ZHIPU_MAX_CONCURRENCY` / `CHATGPT_MAX_CONCURRENCY`）。
- 各 provider 的 `_generate` 保持同步不变（含上次已改的 `raise` 重抛）。

**`AELlmManager`（`AELlmManager.py`）**
- `generate` 改为 `async def generate(...)`：保留 provider 路由、默认回调注入（`_default_think_process` / `_default_delta_process`）、计时、错误 dict 包装；执行体 `response = await provider.generate(question, think_process, delta_process)`。
- `except Exception` 仍返回 `{"response": None, "status": "error", "error": f"{llm_type.value} 调用失败: {str(e)}", "elapsed_seconds": elapsed}`。

**`routes/question.py`**
- 移除：`from concurrent.futures import ThreadPoolExecutor`、模块级 `executor = ThreadPoolExecutor(max_workers=10)`、`_process_llm_sync` 函数、`loop.run_in_executor(...)` 调用。
- `process_question`（本就是 `async def`）改为直接 `await manager.generate(question, think_process=_think_cb, delta_process=_delta_cb)`。
- `_think_cb` / `_delta_cb` 回调定义保留（仍 `question.feed_think` / `question.feed_delta`）。
- 其余（请求解析、llm_type/level 映射、日志、HTTPException）不变。

### 并发配置语义

- 并发上限 = 该 provider 同时进入 `_generate`（即同时调用后端 model）的最大请求数。
- 超出上限的请求在 `async with self._semaphore` 处 `await` 排队等待，有 slot 释放即执行。**无超时、无拒绝**。
- per-provider 独立计数：qwen 满载不影响 claude 的并发。

### 回调线程语义

- `_think_cb` / `_delta_cb` 由 `asyncio.to_thread` 的工作线程调用，与改造前由 `ThreadPoolExecutor` 线程调用的语义一致；`question.feed_think` / `question.feed_delta` 行为不变。

### 错误处理

- 基类 `async generate` 保留 messages/result 日志；`_generate` 已 `raise` 重抛原始异常（上次改动）；manager 保留 dict 错误包装；route 保留 `HTTPException`。错误信息向上传递链与上次改动一致。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `llms/llm_providers/ae_base_provider.py` | `generate` 改 async + Semaphore 框架 + lazy 创建 |
| `llms/llm_providers/ae_qwen_provider.py` | `MAX_CONCURRENCY=1` + `CONCURRENCY_ENV_KEY` |
| `llms/llm_providers/ae_claude_provider.py` | `MAX_CONCURRENCY=10` + `CONCURRENCY_ENV_KEY` |
| `llms/llm_providers/ae_gemini_provider.py` | `MAX_CONCURRENCY=10` + `CONCURRENCY_ENV_KEY` |
| `llms/llm_providers/ae_deepseek_provider.py` | `MAX_CONCURRENCY=10` + `CONCURRENCY_ENV_KEY` |
| `llms/llm_providers/ae_zhipu_provider.py` | `MAX_CONCURRENCY=10` + `CONCURRENCY_ENV_KEY` |
| `llms/llm_providers/ae_chatgpt_provider.py` | `MAX_CONCURRENCY=10` + `CONCURRENCY_ENV_KEY` |
| `llms/AELlmManager.py` | `generate` 改 async 透传 |
| `llms/routes/question.py` | 移除并发控制，直接 `await manager.generate` |

## 测试

项目用 pytest（`pyproject.toml`），`llms/` 下已有 `test_auth.py` / `test_parse_output.py`。建议新增一个并发回归测试：

- 构造一个 `MAX_CONCURRENCY=1` 的假 provider（`_generate` 内 `time.sleep`），并发发起 2 个请求，断言两次执行不重叠（第二次的 start_time ≥ 第一次的 end_time），验证串行语义。

该测试为可选，实现阶段按需添加。

## 兼容性

- `generate` 从同步改 async：唯一调用方 `routes/question.py`（经 `_process_llm_sync`）与 `AELlmManager.py` 会同步改造，无其他外部同步调用方（已 grep 确认）。
- 不影响 `AEQuestion`、各 `model` 层（`qwen_model` 等仍为同步 `requests.post`）。
