#!/usr/bin/env python3
"""
测试 Context 创建接口

测试步骤：
1. 发送创建 Context 请求（包含 aedir）
2. 验证返回的 session_id
3. 查询 Context 状态确认 aedir 已保存
"""

import requests
import json

# 配置
BASE_URL = "http://localhost:8000"

def test_create_context():
    """测试创建 Context"""
    print("\n" + "=" * 60)
    print("测试：创建 Context")
    print("=" * 60)

    # 请求数据
    aedir = "/Users/test/project/myapp"
    request_data = {
        "aedir": aedir
    }

    print(f"\n📤 发送请求:")
    print(f"   URL: {BASE_URL}/ae/context/create")
    print(f"   Body: {json.dumps(request_data, indent=2)}")

    # 发送请求
    response = requests.post(
        f"{BASE_URL}/ae/context/create",
        json=request_data,
        headers={"Content-Type": "application/json"}
    )

    print(f"\n📥 收到响应:")
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")

        session_id = result.get("contextid")
        print(f"\n✅ Context 创建成功!")
        print(f"   Session ID: {session_id}")

        return session_id
    else:
        print(f"   Error: {response.text}")
        print(f"\n❌ Context 创建失败!")
        return None


def test_get_context_stats(session_id):
    """测试获取 Context 统计信息"""
    print("\n" + "=" * 60)
    print("测试：获取 Context 统计信息")
    print("=" * 60)

    print(f"\n📤 发送请求:")
    print(f"   URL: {BASE_URL}/ae/contexts/stats")

    response = requests.get(f"{BASE_URL}/ae/contexts/stats")

    print(f"\n📥 收到响应:")
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

        # 验证 aedir 是否保存
        if session_id in result:
            context_info = result[session_id]
            aedir = context_info.get("aedir")
            print(f"\n✅ Context 信息已找到!")
            print(f"   Session ID: {session_id}")
            print(f"   AE Dir: {aedir}")
            print(f"   Created At: {context_info.get('created_at')}")
            print(f"   Message Count: {context_info.get('message_count')}")
            return True
        else:
            print(f"\n⚠️  未找到 Session ID: {session_id}")
            return False
    else:
        print(f"   Error: {response.text}")
        print(f"\n❌ 获取统计信息失败!")
        return False


def test_empty_aedir():
    """测试空 aedir（应该失败）"""
    print("\n" + "=" * 60)
    print("测试：空 aedir（预期失败）")
    print("=" * 60)

    request_data = {
        "aedir": ""
    }

    print(f"\n📤 发送请求:")
    print(f"   URL: {BASE_URL}/ae/context/create")
    print(f"   Body: {json.dumps(request_data, indent=2)}")

    response = requests.post(
        f"{BASE_URL}/ae/context/create",
        json=request_data,
        headers={"Content-Type": "application/json"}
    )

    print(f"\n📥 收到响应:")
    print(f"   Status Code: {response.status_code}")
    print(f"   Response: {response.text}")

    if response.status_code == 400:
        print(f"\n✅ 正确拒绝了空 aedir!")
    else:
        print(f"\n❌ 应该返回 400 错误!")


def test_multiple_contexts():
    """测试创建多个 Context"""
    print("\n" + "=" * 60)
    print("测试：创建多个 Context")
    print("=" * 60)

    dirs = [
        "/Users/test/project1",
        "/Users/test/project2",
        "/Users/test/project3"
    ]

    session_ids = []

    for aedir in dirs:
        request_data = {"aedir": aedir}
        response = requests.post(
            f"{BASE_URL}/ae/context/create",
            json=request_data
        )

        if response.status_code == 200:
            result = response.json()
            session_id = result.get("contextid")
            session_ids.append(session_id)
            print(f"✅ 创建 Context: {aedir} -> {session_id}")
        else:
            print(f"❌ 创建失败: {aedir}")

    print(f"\n✅ 成功创建 {len(session_ids)} 个 Context")
    return session_ids


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Context 创建接口测试")
    print("=" * 60)
    print("\n⚠️  请确保服务已启动: uvicorn app:app --reload --port 8000")

    try:
        # 测试 1：创建单个 Context
        session_id = test_create_context()

        if session_id:
            # 测试 2：获取 Context 统计信息
            test_get_context_stats(session_id)

        # 测试 3：空 aedir（预期失败）
        test_empty_aedir()

        # 测试 4：创建多个 Context
        test_multiple_contexts()

        print("\n" + "=" * 60)
        print("测试完成!")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到服务器!")
        print("   请确保服务已启动: uvicorn app:app --reload --port 8000")
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
