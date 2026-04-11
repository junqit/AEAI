from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests
import sys
import os

# 添加父目录到路径以导入配置
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from AEIQConfig import config


class AELLMResponse:
    """单个 LLM 的响应结果"""
    def __init__(self, llm_type: str, response: Any, error: Optional[str] = None):
        self.llm_type = llm_type
        self.response = response
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_type": self.llm_type,
            "response": str(self.response) if self.response else None,
            "error": self.error,
            "timestamp": self.timestamp
        }


class AEContext:
    """支持多 LLM 类型并行处理的会话上下文实例"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.llm_service_url = config.get_llm_service_url()
        self.messages: List[Dict[str, Any]] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        # 并发控制：确保单个 Context 内串行处理
        self._lock = asyncio.Lock()
        # 为多个 LLM 并行调用创建线程池
        self._executor = ThreadPoolExecutor(
            max_workers=config.get_executor_max_workers()
        )

    async def process_message(
        self,
        user_input: str,
        llm_types: List[str]
    ) -> List[AELLMResponse]:
        """
        异步处理用户消息 - 并行调用多个 LLM

        Args:
            user_input: 用户输入的消息
            llm_types: 需要调用的 LLM 类型列表

        Returns:
            包含所有 LLM 响应的列表
        """
        async with self._lock:
            # 记录用户消息
            self.messages.append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().isoformat()
            })

            # 并行处理所有 LLM 请求
            loop = asyncio.get_event_loop()
            tasks = []

            for llm_type in llm_types:
                task = loop.run_in_executor(
                    self._executor,
                    self._process_single_llm,
                    user_input,
                    llm_type
                )
                tasks.append(task)

            # 等待所有 LLM 响应
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            responses = []
            for llm_type, result in zip(llm_types, results):
                if isinstance(result, Exception):
                    response = AELLMResponse(
                        llm_type=llm_type,
                        response=None,
                        error=str(result)
                    )
                else:
                    response = result
                responses.append(response)

            # 记录所有响应
            self.messages.append({
                "role": "assistant",
                "responses": [r.to_dict() for r in responses],
                "timestamp": datetime.now().isoformat()
            })

            self.updated_at = datetime.now()
            return responses

    def _process_single_llm(
        self,
        user_input: str,
        llm_type: str
    ) -> AELLMResponse:
        """
        同步处理单个 LLM 的调用 - 通过 HTTP 请求到 9999 端口

        Args:
            user_input: 用户输入
            llm_type: LLM 类型

        Returns:
            LLM 响应结果
        """
        try:
            # 构造请求到 9999 端口的 LLM 服务
            url = f"{self.llm_service_url}/aellms/question"
            payload = {
                "question": user_input,
                "llm_type": llm_type,
                "level": "high"
            }

            # 发送 HTTP POST 请求
            response = requests.post(
                url,
                json=payload,
                timeout=config.get_llm_service_timeout()
            )
            response.raise_for_status()

            result = response.json()

            return AELLMResponse(
                llm_type=llm_type,
                response=result.get("response"),
                error=None
            )

        except requests.exceptions.RequestException as e:
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"HTTP request error for {llm_type}: {str(e)}"
            )
        except Exception as e:
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"Error calling {llm_type}: {str(e)}"
            )

    def get_history(self) -> List[Dict[str, Any]]:
        """获取会话历史"""
        return self.messages

    def clear_history(self):
        """清空历史消息"""
        self.messages = []
        self.updated_at = datetime.now()

    def cleanup(self):
        """清理资源"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "session_id": self.session_id,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
