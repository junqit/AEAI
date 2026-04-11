"""
AE Context API 使用示例

演示如何使用支持多 LLM 类型并行处理的 API
"""
import requests
import json
from typing import List


class AEContextClient:
    """AE Context API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def chat(
        self,
        user_input: str,
        session_id: str,
        llm_types: List[str]
    ):
        """
        发送聊天消息，并行调用多个 LLM

        Args:
            user_input: 用户输入
            session_id: 会话 ID
            llm_types: LLM 类型列表，例如 ["claude", "chatgpt", "deepseek"]

        Returns:
            包含所有 LLM 响应的结果
        """
        url = f"{self.base_url}/ae/context/chat"
        payload = {
            "user_input": user_input,
            "session_id": session_id,
            "llm_types": llm_types
        }

        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def get_history(self, session_id: str):
        """获取会话历史"""
        url = f"{self.base_url}/ae/context/history"
        params = {"session_id": session_id}

        response = requests.post(url, params=params)
        response.raise_for_status()
        return response.json()

    def clear_history(self, session_id: str):
        """清空会话历史"""
        url = f"{self.base_url}/ae/context/clear"
        params = {"session_id": session_id}

        response = requests.post(url, params=params)
        response.raise_for_status()
        return response.json()

    def delete_context(self, session_id: str):
        """删除会话"""
        url = f"{self.base_url}/ae/context/delete"
        params = {"session_id": session_id}

        response = requests.post(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_all_stats(self):
        """获取所有会话统计信息"""
        url = f"{self.base_url}/ae/contexts/stats"

        response = requests.get(url)
        response.raise_for_status()
        return response.json()


def main():
    """示例：并行调用多个 LLM"""
    client = AEContextClient()

    # 示例 1: 并行调用 Claude 和 ChatGPT
    print("=" * 60)
    print("示例 1: 并行调用多个 LLM")
    print("=" * 60)

    try:
        result = client.chat(
            user_input="什么是人工智能？",
            session_id="test_session_001",
            llm_types=["claude", "chatgpt", "deepseek"]
        )

        print(f"\n会话 ID: {result['session_id']}")
        print(f"用户输入: {result['user_input']}")
        print("\nLLM 响应:")

        for llm_type, response_data in result['llm_responses'].items():
            print(f"\n--- {llm_type.upper()} ---")
            if response_data['error']:
                print(f"错误: {response_data['error']}")
            else:
                print(f"响应: {response_data['response']}")
            print(f"时间戳: {response_data['timestamp']}")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")

    # 示例 2: 获取会话历史
    print("\n" + "=" * 60)
    print("示例 2: 获取会话历史")
    print("=" * 60)

    try:
        history = client.get_history("test_session_001")
        print(f"\n会话 ID: {history['session_id']}")
        print(f"历史消息数: {len(history['history'])}")

        for i, message in enumerate(history['history'], 1):
            print(f"\n消息 {i}:")
            print(f"  角色: {message['role']}")
            if message['role'] == 'user':
                print(f"  内容: {message['content']}")
            else:
                print(f"  响应数: {len(message['responses'])}")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")

    # 示例 3: 获取统计信息
    print("\n" + "=" * 60)
    print("示例 3: 获取统计信息")
    print("=" * 60)

    try:
        stats = client.get_all_stats()
        print(f"\n活跃会话数: {stats['active_sessions']}")

        for session_id, session_stats in stats['sessions'].items():
            print(f"\n会话: {session_id}")
            print(f"  消息数: {session_stats['message_count']}")
            print(f"  创建时间: {session_stats['created_at']}")
            print(f"  更新时间: {session_stats['updated_at']}")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")

    # 示例 4: 只调用单个 LLM
    print("\n" + "=" * 60)
    print("示例 4: 只调用单个 LLM (Claude)")
    print("=" * 60)

    try:
        result = client.chat(
            user_input="解释一下量子计算",
            session_id="test_session_002",
            llm_types=["claude"]  # 只调用一个 LLM
        )

        print(f"\n会话 ID: {result['session_id']}")
        for llm_type, response_data in result['llm_responses'].items():
            print(f"\n{llm_type}: {response_data['response']}")

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    main()
