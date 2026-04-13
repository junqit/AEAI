"""
QuestionCache 使用示例
"""
from QuestionCache import QuestionCacheStore, ContextBuilder


def example_basic_usage():
    """基础使用示例"""
    print("=== 基础使用示例 ===\n")

    # 1. 创建缓存存储（启用持久化）
    cache = QuestionCacheStore(enable_persistence=True)

    # 2. 添加用户问题
    session_id = "test_session_001"
    cache.add_question(
        session_id=session_id,
        question="什么是机器学习？",
        metadata={"source": "web_chat"}
    )

    # 3. 添加LLM回复
    cache.add_response(
        session_id=session_id,
        response="机器学习是人工智能的一个分支...",
        llm_type="gpt-4",
        metadata={"model": "gpt-4-turbo", "tokens": 150}
    )

    # 4. 继续对话
    cache.add_question(
        session_id=session_id,
        question="能举个例子吗？"
    )

    cache.add_response(
        session_id=session_id,
        response="当然，比如图像识别...",
        llm_type="claude-3"
    )

    # 5. 获取历史记录
    history = cache.get_session_history(session_id)
    print(f"总共 {len(history)} 条记录：")
    for entry in history:
        print(f"  [{entry.role.value}] {entry.content[:50]}...")

    print()


def example_context_building():
    """上下文构建示例"""
    print("=== 上下文构建示例 ===\n")

    cache = QuestionCacheStore()
    builder = ContextBuilder(cache)

    session_id = "test_session_002"

    # 模拟多轮对话
    conversations = [
        ("你好", "你好！我是AI助手，有什么可以帮你的？"),
        ("Python如何读取文件？", "在Python中，可以使用open()函数读取文件..."),
        ("那写入文件呢？", "写入文件也使用open()函数，但需要指定'w'或'a'模式..."),
    ]

    for question, response in conversations:
        cache.add_question(session_id, question)
        cache.add_response(session_id, response, "gpt-4")

    # 构建标准上下文（用于LLM API）
    context = builder.build_context(
        session_id=session_id,
        max_turns=2,  # 只保留最近2轮对话
        include_system_prompt=True
    )

    print("构建的上下文消息：")
    for msg in context:
        print(f"  [{msg['role']}] {msg['content'][:60]}...")

    print()

    # 获取统计信息
    stats = builder.get_context_stats(session_id)
    print(f"上下文统计：")
    print(f"  对话轮数: {stats['total_turns']}")
    print(f"  估算tokens: {stats['estimated_tokens']}")

    print()


def example_multi_llm():
    """多LLM场景示例"""
    print("=== 多LLM场景示例 ===\n")

    cache = QuestionCacheStore()
    builder = ContextBuilder(cache)

    session_id = "test_session_003"

    # 一个问题，多个LLM回复
    cache.add_question(session_id, "介绍一下量子计算")

    # 多个不同的LLM回复
    cache.add_response(
        session_id,
        "量子计算是一种利用量子力学原理...",
        "gpt-4"
    )
    cache.add_response(
        session_id,
        "量子计算机使用量子比特(qubit)进行计算...",
        "claude-3"
    )

    # 获取对话轮次
    turns = cache.get_conversation_turns(session_id)
    print(f"对话轮次: {len(turns)}")
    for turn in turns:
        print(f"  问题: {turn.question.content[:40]}...")
        print(f"  回复数量: {len(turn.responses)}")
        for resp in turn.responses:
            print(f"    - [{resp.llm_type}] {resp.content[:50]}...")

    print()

    # 构建上下文时选择特定LLM的回复
    context = builder.build_context_with_llm_selection(
        session_id=session_id,
        preferred_llm="gpt-4",
        include_system_prompt=False
    )

    print("选择GPT-4的回复构建上下文：")
    for msg in context:
        print(f"  [{msg['role']}] {msg['content'][:60]}...")

    print()


def example_persistence():
    """持久化示例"""
    print("=== 持久化示例 ===\n")

    # 创建缓存（指定存储目录）
    cache = QuestionCacheStore(
        cache_dir="./example_cache",
        enable_persistence=True
    )

    session_id = "persistent_session"

    # 添加数据
    cache.add_question(session_id, "测试持久化")
    cache.add_response(session_id, "持久化正常工作", "gpt-4")

    print("数据已保存到磁盘")

    # 创建新的缓存实例（模拟程序重启）
    cache2 = QuestionCacheStore(
        cache_dir="./example_cache",
        enable_persistence=True
    )

    # 从磁盘加载
    history = cache2.get_session_history(session_id)
    print(f"从磁盘加载了 {len(history)} 条记录")

    # 获取统计
    stats = cache2.get_stats()
    print(f"缓存统计: {stats}")

    print()


def example_token_limit():
    """Token限制示例"""
    print("=== Token限制示例 ===\n")

    cache = QuestionCacheStore()
    builder = ContextBuilder(cache)

    session_id = "token_limit_session"

    # 添加很多对话
    for i in range(10):
        cache.add_question(session_id, f"问题 {i+1}: " + "x" * 100)
        cache.add_response(session_id, f"回答 {i+1}: " + "y" * 200, "gpt-4")

    # 不限制token
    full_context = builder.build_context(session_id, include_system_prompt=False)
    print(f"完整上下文: {len(full_context)} 条消息")

    # 限制token数量
    limited_context = builder.build_context(
        session_id,
        max_tokens=500,  # 限制约500个token
        include_system_prompt=False
    )
    print(f"限制后上下文: {len(limited_context)} 条消息")

    print()


if __name__ == "__main__":
    # 运行所有示例
    example_basic_usage()
    example_context_building()
    example_multi_llm()
    example_persistence()
    example_token_limit()

    print("\n=== 所有示例运行完成 ===")
