from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests
import sys
import os
import logging

# 添加父目录到路径以导入配置
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from AEIQConfig import config

# 导入QuestionCache模块
from .QuestionCache import QuestionCacheStore, ContextBuilder

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


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

    def __init__(self, session_id: str, enable_cache: bool = True):
        self.session_id = session_id
        self.llm_service_url = config.get_llm_service_url()
        self.messages: List[Dict[str, Any]] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        logger.info(f"🚀 初始化 AEContext - session_id={session_id}, enable_cache={enable_cache}, llm_service_url={self.llm_service_url}")

        # 并发控制：确保单个 Context 内串行处理
        self._lock = asyncio.Lock()
        # 为多个 LLM 并行调用创建线程池
        self._executor = ThreadPoolExecutor(
            max_workers=config.get_executor_max_workers()
        )
        logger.info(f"✅ 线程池已创建 - max_workers={config.get_executor_max_workers()}")

        # QuestionCache集成
        self.enable_cache = enable_cache
        if self.enable_cache:
            try:
                self.cache_store = QuestionCacheStore(enable_persistence=True)
                self.context_builder = ContextBuilder(self.cache_store)
                logger.info(f"✅ QuestionCache 已启用 - session_id={session_id}")
            except Exception as e:
                logger.error(f"❌ QuestionCache 初始化失败 - session_id={session_id}, error={str(e)}", exc_info=True)
                self.enable_cache = False

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
        logger.info(f"📥 收到用户消息 - session_id={self.session_id}, user_input_length={len(user_input)}, llm_types={llm_types}")
        logger.debug(f"📝 用户输入内容: {user_input[:200]}...")

        async with self._lock:
            try:
                # 记录用户消息
                self.messages.append({
                    "role": "user",
                    "content": user_input,
                    "timestamp": datetime.now().isoformat()
                })
                logger.info(f"✅ 用户消息已记录 - session_id={self.session_id}, total_messages={len(self.messages)}")

                # 使用QuestionCache记录用户问题
                if self.enable_cache:
                    try:
                        self.cache_store.add_question(
                            session_id=self.session_id,
                            question=user_input,
                            metadata={"llm_types": llm_types}
                        )
                        logger.debug(f"✅ QuestionCache 已记录问题 - session_id={self.session_id}")
                    except Exception as e:
                        logger.error(f"❌ QuestionCache 记录问题失败 - session_id={self.session_id}, error={str(e)}")

                # 并行处理所有 LLM 请求
                logger.info(f"🔄 开始并行调用 {len(llm_types)} 个 LLM - session_id={self.session_id}")
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
                logger.info(f"✅ 所有 LLM 调用完成 - session_id={self.session_id}, results_count={len(results)}")

                # 处理结果
                responses = []
                success_count = 0
                error_count = 0

                for llm_type, result in zip(llm_types, results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ LLM 调用异常 - session_id={self.session_id}, llm_type={llm_type}, exception={str(result)}", exc_info=result)
                        response = AELLMResponse(
                            llm_type=llm_type,
                            response=None,
                            error=str(result)
                        )
                        error_count += 1
                    else:
                        response = result
                        if response.error:
                            logger.warning(f"⚠️ LLM 返回错误 - session_id={self.session_id}, llm_type={llm_type}, error={response.error}")
                            error_count += 1
                        else:
                            logger.info(f"✅ LLM 调用成功 - session_id={self.session_id}, llm_type={llm_type}, response_length={len(str(response.response)) if response.response else 0}")
                            success_count += 1
                    responses.append(response)

                    # 使用QuestionCache记录LLM回复
                    if self.enable_cache and not response.error:
                        try:
                            self.cache_store.add_response(
                                session_id=self.session_id,
                                response=str(response.response) if response.response else "",
                                llm_type=response.llm_type,
                                metadata={"timestamp": response.timestamp}
                            )
                            logger.debug(f"✅ QuestionCache 已记录响应 - session_id={self.session_id}, llm_type={response.llm_type}")
                        except Exception as e:
                            logger.error(f"❌ QuestionCache 记录响应失败 - session_id={self.session_id}, llm_type={response.llm_type}, error={str(e)}")

                logger.info(f"📊 处理结果统计 - session_id={self.session_id}, success={success_count}, error={error_count}, total={len(responses)}")

                # # 记录所有响应
                # self.messages.append({
                #     "role": "assistant",
                #     "responses": [r.to_dict() for r in responses],
                #     "timestamp": datetime.now().isoformat()
                # })

                self.updated_at = datetime.now()
                return responses

            except Exception as e:
                logger.error(f"❌ process_message 执行失败 - session_id={self.session_id}, error={str(e)}", exc_info=True)
                raise

    def _process_single_llm(
        self,
        user_input: str,
        llm_type: str
    ) -> AELLMResponse:
        """
        同步处理单个 LLM 的调用 - 通过 HTTP 请求到 9999 端口
        请求参数完全匹配 question.py 中的 AEQuestionRequest 格式

        Args:
            user_input: 用户输入
            llm_type: LLM 类型

        Returns:
            LLM 响应结果
        """
        logger.info(f"🔄 开始调用 LLM - session_id={self.session_id}, llm_type={llm_type}")
        start_time = datetime.now()

        try:
            # 参数格式严格匹配 question.py 中的 AEQuestionRequest
            url = f"{self.llm_service_url}/aellms/question"

            logger.debug(f"📦 准备请求参数 - session_id={self.session_id}, llm_type={llm_type}, messages_count={len(self.messages)}")

            payload = {
                "messages": self.messages,
                "llm_type": llm_type,
                "level": "high"
            }

            logger.info(f"📤 发送 HTTP 请求 - session_id={self.session_id}, llm_type={llm_type}, url={url}")
            logger.debug(f"📋 请求 payload: {payload}")

            # 发送 HTTP POST 请求
            response = requests.post(
                url,
                json=payload,
                timeout=config.get_llm_service_timeout()
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"📥 收到 HTTP 响应 - session_id={self.session_id}, llm_type={llm_type}, status_code={response.status_code}, elapsed={elapsed:.2f}s")

            response.raise_for_status()

            result = response.json()
            logger.debug(f"📄 响应内容: {str(result)[:500]}...")

            llm_response = AELLMResponse(
                llm_type=llm_type,
                response=result.get("response"),
                error=None
            )

            logger.info(f"✅ LLM 调用成功 - session_id={self.session_id}, llm_type={llm_type}, elapsed={elapsed:.2f}s, response_length={len(str(llm_response.response)) if llm_response.response else 0}")

            return llm_response

        except requests.exceptions.Timeout as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            error_msg = f"请求超时 - timeout={config.get_llm_service_timeout()}s"
            logger.error(f"❌ {error_msg} - session_id={self.session_id}, llm_type={llm_type}, elapsed={elapsed:.2f}s", exc_info=True)
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"HTTP request timeout for {llm_type}: {error_msg}"
            )
        except requests.exceptions.ConnectionError as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            error_msg = f"连接错误 - url={self.llm_service_url}"
            logger.error(f"❌ {error_msg} - session_id={self.session_id}, llm_type={llm_type}, elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"HTTP connection error for {llm_type}: {str(e)}"
            )
        except requests.exceptions.HTTPError as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            status_code = e.response.status_code if e.response else "unknown"
            error_msg = f"HTTP 错误 - status_code={status_code}"
            logger.error(f"❌ {error_msg} - session_id={self.session_id}, llm_type={llm_type}, elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"HTTP error for {llm_type}: {str(e)}"
            )
        except requests.exceptions.RequestException as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ HTTP 请求异常 - session_id={self.session_id}, llm_type={llm_type}, elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"HTTP request error for {llm_type}: {str(e)}"
            )
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ 未知错误 - session_id={self.session_id}, llm_type={llm_type}, elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return AELLMResponse(
                llm_type=llm_type,
                response=None,
                error=f"Error calling {llm_type}: {str(e)}"
            )

    def get_history(self) -> List[Dict[str, Any]]:
        """获取会话历史"""
        logger.debug(f"📚 获取历史记录 - session_id={self.session_id}, message_count={len(self.messages)}")
        return self.messages

    def clear_history(self):
        """清空历史消息"""
        old_count = len(self.messages)
        self.messages = []
        self.updated_at = datetime.now()
        logger.info(f"🗑️ 清空历史记录 - session_id={self.session_id}, cleared_count={old_count}")

    def cleanup(self):
        """清理资源"""
        logger.info(f"🧹 开始清理资源 - session_id={self.session_id}")
        try:
            if hasattr(self, '_executor'):
                self._executor.shutdown(wait=False)
                logger.info(f"✅ 线程池已关闭 - session_id={self.session_id}")
        except Exception as e:
            logger.error(f"❌ 清理资源失败 - session_id={self.session_id}, error={str(e)}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "session_id": self.session_id,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
        logger.debug(f"📊 获取统计信息 - session_id={self.session_id}, stats={stats}")
        return stats

    def get_context_for_next_call(
        self,
        max_turns: int = 5,
        max_tokens: Optional[int] = None,
        preferred_llm: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        获取下次LLM调用的上下文

        Args:
            max_turns: 最大对话轮数
            max_tokens: 最大token数量限制
            preferred_llm: 优先使用的LLM类型（用于选择特定LLM的回复）

        Returns:
            标准格式的上下文消息列表
        """
        logger.info(f"🔍 获取下次调用上下文 - session_id={self.session_id}, max_turns={max_turns}, max_tokens={max_tokens}, preferred_llm={preferred_llm}")

        if not self.enable_cache:
            logger.warning(f"⚠️ QuestionCache 未启用 - session_id={self.session_id}, 返回空上下文")
            return []

        try:
            if preferred_llm:
                context = self.context_builder.build_context_with_llm_selection(
                    session_id=self.session_id,
                    preferred_llm=preferred_llm,
                    max_turns=max_turns
                )
                logger.info(f"✅ 上下文构建成功（指定LLM） - session_id={self.session_id}, preferred_llm={preferred_llm}, context_length={len(context)}")
            else:
                context = self.context_builder.build_context(
                    session_id=self.session_id,
                    max_turns=max_turns,
                    max_tokens=max_tokens
                )
                logger.info(f"✅ 上下文构建成功 - session_id={self.session_id}, context_length={len(context)}")

            return context

        except Exception as e:
            logger.error(f"❌ 上下文构建失败 - session_id={self.session_id}, error={str(e)}", exc_info=True)
            return []
