"""测试 Context 管理器"""

from Context import Context, ContextManager
from llms.question.AEQuestion import LLMType
from llms.AEAiLevel import AEAiLevel


def test_context_manager():
    """测试 Context 管理器基本功能"""
    print("=" * 50)
    print("测试 Context 管理器")
    print("=" * 50)

    # 创建管理器
    manager = ContextManager()

    # 测试获取或创建
    context1 = manager.get_or_create_context("user_001")
    context2 = manager.get_or_create_context("user_002")
    context1_again = manager.get_or_create_context("user_001")

    assert context1 is context1_again, "同一 ID 应返回相同实例"
    assert context1 is not context2, "不同 ID 应返回不同实例"
    print("✓ 获取或创建 Context 成功")

    # 测试活跃数量
    assert manager.get_active_count() == 2, "应该有 2 个活跃 Context"
    print(f"✓ 活跃 Context 数量: {manager.get_active_count()}")

    # 测试删除
    success = manager.delete_context("user_002")
    assert success, "删除应该成功"
    assert manager.get_active_count() == 1, "删除后应该剩 1 个"
    print("✓ 删除 Context 成功")

    # 测试获取不存在的 Context
    context = manager.get_context("not_exist")
    assert context is None, "不存在的 Context 应返回 None"
    print("✓ 获取不存在的 Context 返回 None")


def test_context_instance():
    """测试 Context 实例"""
    print("\n" + "=" * 50)
    print("测试 Context 实例")
    print("=" * 50)

    context = Context("test_user", LLMType.CLAUDE, AEAiLevel.default)

    # 测试属性
    assert context.session_id == "test_user"
    assert context.llm_type == LLMType.CLAUDE
    assert context.level == AEAiLevel.default
    assert len(context.messages) == 0
    print("✓ Context 属性初始化正确")

    # 测试清空历史
    context.messages.append({"role": "user", "content": "test"})
    context.clear_history()
    assert len(context.messages) == 0
    print("✓ 清空历史成功")


def test_singleton_pattern():
    """测试单例模式"""
    print("\n" + "=" * 50)
    print("测试单例模式")
    print("=" * 50)

    manager1 = ContextManager()
    manager2 = ContextManager()

    assert manager1 is manager2, "ContextManager 应该是单例"
    print("✓ ContextManager 单例模式正确")


if __name__ == "__main__":
    print("\n🚀 Context 管理器测试\n")

    try:
        test_context_manager()
        test_context_instance()
        test_singleton_pattern()

        print("\n" + "=" * 50)
        print("✅ 所有测试通过")
        print("=" * 50 + "\n")

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}\n")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}\n")
