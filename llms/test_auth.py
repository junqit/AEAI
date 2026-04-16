#!/usr/bin/env python3
"""
API Key 认证测试脚本
测试全局中间件认证是否正常工作
"""

import requests
import json

# 配置
BASE_URL = "http://localhost:9999"
API_KEY = "ae-agent-2024-fixed-key-9527"  # 正确的 API Key
WRONG_KEY = "wrong-key-123"

def test_without_api_key():
    """测试：不提供 API Key"""
    print("\n🧪 测试 1: 不提供 API Key")
    print("-" * 50)

    response = requests.post(
        f"{BASE_URL}/aellms/question",
        headers={"Content-Type": "application/json"},
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "llm_type": "claude"
        }
    )

    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    if response.status_code == 401:
        print("✅ 测试通过：正确拦截了缺少 API Key 的请求")
    else:
        print("❌ 测试失败：应该返回 401")


def test_with_wrong_api_key():
    """测试：提供错误的 API Key"""
    print("\n🧪 测试 2: 提供错误的 API Key")
    print("-" * 50)

    response = requests.post(
        f"{BASE_URL}/aellms/question",
        headers={
            "Content-Type": "application/json",
            "AE-API-Key": WRONG_KEY
        },
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "llm_type": "claude"
        }
    )

    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    if response.status_code == 401:
        print("✅ 测试通过：正确拦截了错误的 API Key")
    else:
        print("❌ 测试失败：应该返回 401")


def test_with_correct_api_key():
    """测试：提供正确的 API Key"""
    print("\n🧪 测试 3: 提供正确的 API Key")
    print("-" * 50)

    response = requests.post(
        f"{BASE_URL}/aellms/question",
        headers={
            "Content-Type": "application/json",
            "AE-API-Key": API_KEY
        },
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "llm_type": "claude"
        }
    )

    print(f"状态码: {response.status_code}")
    print(f"响应预览: {str(response.json())[:200]}...")

    if response.status_code in [200, 500]:  # 200 成功，500 是业务逻辑错误（非认证错误）
        print("✅ 测试通过：正确通过了 API Key 验证")
    else:
        print(f"❌ 测试失败：应该返回 200 或 500，实际返回 {response.status_code}")


def test_health_endpoint():
    """测试：健康检查接口（不需要认证）"""
    print("\n🧪 测试 4: 健康检查接口（不需要认证）")
    print("-" * 50)

    response = requests.get(f"{BASE_URL}/health")

    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    if response.status_code == 200:
        print("✅ 测试通过：健康检查接口无需认证")
    else:
        print("❌ 测试失败：健康检查应该返回 200")


def test_docs_endpoint():
    """测试：API 文档接口（不需要认证）"""
    print("\n🧪 测试 5: API 文档接口（不需要认证）")
    print("-" * 50)

    response = requests.get(f"{BASE_URL}/docs")

    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        print("✅ 测试通过：API 文档无需认证")
    else:
        print("❌ 测试失败：API 文档应该返回 200")


if __name__ == "__main__":
    print("=" * 50)
    print("API Key 全局认证测试")
    print("=" * 50)
    print(f"目标服务: {BASE_URL}")
    print(f"API Key: {API_KEY}")

    try:
        # 测试不需要认证的接口
        test_health_endpoint()
        test_docs_endpoint()

        # 测试需要认证的接口
        test_without_api_key()
        test_with_wrong_api_key()
        test_with_correct_api_key()

        print("\n" + "=" * 50)
        print("测试完成！")
        print("=" * 50)

    except requests.exceptions.ConnectionError:
        print("\n❌ 错误：无法连接到服务器")
        print(f"请确保服务已启动: python app.py")
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
