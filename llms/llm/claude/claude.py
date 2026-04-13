"""
Claude API 模型类
封装 Claude API 的调用、配置和资源管理
"""
import requests
import json
from typing import Optional, List, Dict, Any


class AEClaudeModel:
    """Claude API 模型封装类"""

    def __init__(self, base_url: str = None, auth_token: str = None):
        """
        初始化 Claude 模型

        Args:
            base_url: API 基础 URL
            auth_token: 认证 token
        """
        self.base_url = base_url or "http://model.mify.ai.srv/anthropic"
        self.auth_token = auth_token or "sk-psTx7IFlW79l67Or8JqLsBL0CqCtkhVlHoOMfRMts1Ugkdiu"
        self.is_loaded = False

    def load(self):
        """
        加载 Claude API 配置

        Raises:
            Exception: 配置验证失败时抛出异常
        """
        if self.is_loaded:
            print("Claude API 已配置，跳过重复加载")
            return

        try:
            # 验证配置
            if not self.base_url:
                raise ValueError("base_url 不能为空")
            if not self.auth_token:
                raise ValueError("auth_token 不能为空")

            self.is_loaded = True
            print(f"✅ Claude API 配置成功！")
            print(f"   Base URL: {self.base_url}")

        except Exception as e:
            print(f"❌ Claude API 配置失败: {str(e)}")
            self.cleanup()
            raise

    def generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """
        使用 Claude API 生成文本

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
            system: 系统提示词
            tools: 工具列表
            max_tokens: 最大 token 数
            temperature: 温度参数

        Returns:
            dict: API 响应结果

        Raises:
            Exception: API 调用失败时抛出异常
        """
        if not self.is_loaded:
            self.load()

        try:
            # 1. 构建 URL
            url = f"{self.base_url}/v1/messages"

            # 2. 构建 headers
            headers = {
                "x-api-key": self.auth_token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            # 3. 构建 payload
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages
            }

            # 4. 打印请求信息
            print(f"Claude API Request:")
            print(f"  Model: {model}")
            print(f"  Messages: {messages}")

            # 5. 发送请求
            response = requests.post(url, headers=headers, json=payload)

            # 6. 处理响应
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                return f"请求失败: {response.status_code}"

        except Exception as e:
            return f"请求异常: {e}"

    def get_status(self) -> dict:
        """
        获取模型状态

        Returns:
            dict: 包含模型状态信息的字典
        """
        return {
            "base_url": self.base_url,
            "is_loaded": self.is_loaded,
            "api_type": "claude"
        }

    def cleanup(self):
        """清理资源"""
        self.is_loaded = False
        print("🧹 Claude API 资源已清理")


# 全局单例实例
_claude_model_instance: Optional[AEClaudeModel] = None


def get_claude_model(base_url: str = None, auth_token: str = None) -> AEClaudeModel:
    """
    获取 Claude 模型单例实例

    Args:
        base_url: API 基础 URL（仅首次调用时有效）
        auth_token: 认证 token（仅首次调用时有效）

    Returns:
        AEClaudeModel: Claude 模型实例
    """
    global _claude_model_instance
    if _claude_model_instance is None:
        _claude_model_instance = AEClaudeModel(base_url, auth_token)
    return _claude_model_instance


def cleanup_claude_model():
    """清理全局 Claude 模型实例"""
    global _claude_model_instance
    if _claude_model_instance is not None:
        _claude_model_instance.cleanup()
        _claude_model_instance = None


# ==================== 向后兼容的函数 ====================
# 保留原有的 call_claude_api 函数以保持向后兼容

def call_claude_api(
    messages: list,
    model: str,
    system: str = None,
    tools: list = None,
    max_tokens: int = 4096,
    temperature: float = 0.0
):
    """
    调用 Claude API（向后兼容函数）

    Args:
        messages: 消息列表 [{"role": "user", "content": "..."}]
        model: 模型名称
        system: 系统提示词
        tools: 工具列表
        max_tokens: 最大 token 数
        temperature: 温度参数

    Returns:
        dict: API 响应结果
    """
    claude_model = get_claude_model()
    return claude_model.generate(
        messages=messages,
        model=model,
        system=system,
        tools=tools,
        max_tokens=max_tokens,
        temperature=temperature
    )



# def call_claude_api_stream(message, system=None, tools=None, level=AEAiLevel.default):

#     # 从配置中读取参数
#     base_url = "http://model.mify.ai.srv/anthropic"
#     auth_token = "sk-psTx7IFlW79l67Or8JqLsBL0CqCtkhVlHoOMfRMts1Ugkdiu"

#     model = "ppio/pa/claude-haiku-4-5-20251001"  # 或使用其他模型
#     if level == AEAiLevel.high:
#         model = "ppio/pa/claude-opus-4-6"
#     elif level == AEAiLevel.middle:
#         model = "ppio/pa/claude-sonnet-4-5-20250929"

#     url = f"{base_url}/v1/messages"
#     headers = {
#         "x-api-key": auth_token,
#         "anthropic-version": "2023-06-01",
#         "content-type": "application/json"
#     }

#     payload = {
#         "model": model,
#         "max_tokens": 4096,
#         "temperature": 0.7,
#         "stream": True,
#         "messages": message
#     }

#     if system:
#         payload["system"] = system

#     if tools:
#         payload["tools"] = tools

#     try:
#         response = requests.post(url, headers=headers, json=payload, stream=True)
    
#         if response.status_code == 200:
#             for line in response.iter_lines():
#                 if line:
#                     line = line.decode('utf-8')
#                     if line.startswith('data: '):
#                         data = line[6:]
#                         if data == '[DONE]':
#                             break
#                         try:
#                             chunk = json.loads(data)

#                             # Claude API 的流式响应格式
#                             if 'delta' in chunk.get('content', [{}])[0]:
#                                 text = chunk['content'][0]['delta'].get('text', '')
#                                 if text:
#                                     yield text  # 逐字返回

#                         except json.JSONDecodeError:
#                             continue
#                     else:
#                         yield f"错误: {response.status_code}"
            
#     except Exception as e:
#         return f"请求异常: {e}"