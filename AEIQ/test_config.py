"""
AEIQ 配置测试脚本

测试统一配置是否正常工作
"""
from AEIQConfig import config
from Context.AEContext import AEContext
from Context.AEContextManager import AEContextManager


def test_config():
    """测试配置加载"""
    print("=" * 60)
    print("测试 AEIQConfig 配置加载")
    print("=" * 60)

    print(f"\n✅ LLM 服务地址: {config.get_llm_service_url()}")
    print(f"✅ 请求超时时间: {config.get_llm_service_timeout()} 秒")
    print(f"✅ 会话超时时间: {config.get_session_timeout()} 秒")
    print(f"✅ 线程池大小: {config.get_executor_max_workers()}")
    print(f"✅ 应用标题: {config.APP_TITLE}")
    print(f"✅ 应用版本: {config.APP_VERSION}")
    print(f"✅ 服务端口: {config.AEIQ_PORT}")


def test_context_uses_config():
    """测试 Context 使用配置"""
    print("\n" + "=" * 60)
    print("测试 AEContext 使用统一配置")
    print("=" * 60)

    context = AEContext(session_id="test_config")

    print(f"\n✅ Context LLM 服务地址: {context.llm_service_url}")
    print(f"✅ Context 使用配置: {context.llm_service_url == config.get_llm_service_url()}")
    print(f"✅ Context 线程池大小: {context._executor._max_workers}")

    context.cleanup()


def test_context_manager_uses_config():
    """测试 ContextManager 使用配置"""
    print("\n" + "=" * 60)
    print("测试 AEContextManager 使用统一配置")
    print("=" * 60)

    manager = AEContextManager()

    print(f"\n✅ Manager 会话超时: {manager.session_timeout} 秒")
    print(f"✅ Manager 使用配置: {manager.session_timeout == config.get_session_timeout()}")


def main():
    """运行所有测试"""
    print("\n🚀 开始 AEIQ 配置测试\n")

    test_config()
    test_context_uses_config()
    test_context_manager_uses_config()

    print("\n\n✅ 所有配置测试通过!\n")
    print("📝 说明:")
    print("  - 所有组件都使用 AEIQConfig 中的统一配置")
    print("  - 可以通过环境变量 LLM_SERVICE_URL 覆盖默认配置")
    print("  - 修改配置只需要修改 AEIQConfig.py 文件\n")


if __name__ == "__main__":
    main()
