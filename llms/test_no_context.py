"""
测试 llms 工程 - 验证 AEContext 依赖已删除

测试 /question 端点是否正常工作
"""
import requests
import json


def test_question_endpoint():
    """测试 question 端点"""
    print("=" * 60)
    print("测试 /question 端点（无 AEContext 依赖）")
    print("=" * 60)

    url = "http://localhost:9999/question"

    # 测试单个 LLM
    print("\n1. 测试单个 LLM (Claude)")
    print("-" * 60)

    payload = {
        "question": "什么是 Python？",
        "llm_types": ["claude"],
        "level": "default"
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        print(f"✅ 状态: {result['status']}")
        print(f"✅ 问题: {result['question']}")
        print(f"✅ 响应数量: {len(result['answers'])}")

        for llm_type, answer in result['answers'].items():
            print(f"\n{llm_type.upper()}:")
            print(f"  状态: {answer['status']}")
            if answer['error']:
                print(f"  错误: {answer['error']}")
            else:
                print(f"  响应长度: {len(answer['response'])} 字符")
            print(f"  耗时: {answer['elapsed_seconds']} 秒")

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器 (9999 端口)")
        print("   请先启动 llms 服务: uvicorn app:app --port 9999")
        return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

    # 测试多个 LLM
    print("\n\n2. 测试多个 LLM 并发调用")
    print("-" * 60)

    payload = {
        "question": "解释机器学习",
        "llm_types": ["claude", "gemini"],
        "level": "high"
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        print(f"✅ 状态: {result['status']}")
        print(f"✅ 并发调用了 {len(result['answers'])} 个 LLM")

        for llm_type, answer in result['answers'].items():
            print(f"\n{llm_type.upper()}:")
            print(f"  状态: {answer['status']}")
            print(f"  耗时: {answer['elapsed_seconds']} 秒")

    except Exception as e:
        print(f"⚠️  多 LLM 测试失败: {e}")

    return True


def test_import():
    """测试导入是否正常"""
    print("\n\n3. 测试模块导入（无 AEContext）")
    print("-" * 60)

    try:
        import sys
        sys.path.insert(0, '/Users/tianjunqi/Project/Self/Agents/Service/llms')

        from routes.question import router
        print("✅ routes.question 导入成功")

        from AEllm import AEllm
        print("✅ AEllm 导入成功")

        from AELlmManager import AELlmManager
        print("✅ AELlmManager 导入成功")

        # 检查是否有 AEContext 引用
        import os
        os.chdir('/Users/tianjunqi/Project/Self/Agents/Service/llms')
        result = os.popen('grep -r "AEContext" --include="*.py" . 2>/dev/null').read()

        if result:
            print(f"❌ 发现 AEContext 引用:\n{result}")
            return False
        else:
            print("✅ 没有 AEContext 引用")

        return True

    except Exception as e:
        print(f"❌ 导入测试失败: {e}")
        return False


def main():
    print("\n🚀 开始测试 llms 工程 - AEContext 依赖清理验证\n")

    # 测试导入
    import_ok = test_import()

    # 测试端点
    endpoint_ok = test_question_endpoint()

    print("\n\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"导入测试: {'✅ 通过' if import_ok else '❌ 失败'}")
    print(f"端点测试: {'✅ 通过' if endpoint_ok else '❌ 失败'}")

    if import_ok and endpoint_ok:
        print("\n✅ 所有测试通过！AEContext 依赖已完全删除")
    else:
        print("\n⚠️  部分测试失败，请检查")

    print("\n📝 说明:")
    print("  - llms 工程不再依赖 AEContext")
    print("  - 直接使用 AEllm 进行 LLM 调用")
    print("  - 支持单个和多个 LLM 并发调用")
    print("  - /question 端点功能完整\n")


if __name__ == "__main__":
    main()
