from enum import Enum
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from AEAiLevel import AEAiLevel
from llm.claude.claude import call_claude_api
from question.AEQuestion import LLMType, AEQuestion

class AEllm:
    """
    统一的 LLM 调用接口类
    支持多种 LLM 类型：Claude、ChatGPT、DeepSeek 等
    """

    @staticmethod
    def call_llm(question: AEQuestion, llm_type: LLMType = LLMType.CLAUDE, level: AEAiLevel = AEAiLevel.default):

        # 根据 LLM 类型调用对应的 API
        if llm_type == LLMType.CLAUDE:
            # 将问题转换为消息格式
            messages = question.to_messages()

            # 根据 level 选择模型
            model_map = {
                AEAiLevel.default: "claude-3-5-sonnet-20241022",
                AEAiLevel.middle: "claude-3-5-sonnet-20241022",
                AEAiLevel.high: "claude-3-7-sonnet-20250219"
            }
            model = model_map.get(level, "claude-3-5-sonnet-20241022")

            return call_claude_api(
                messages=messages,
                model=model,
                system=question.system,
                tools=question.tools
            )
        elif llm_type == LLMType.CHATGPT:
            raise NotImplementedError("ChatGPT API 调用尚未实现")
        elif llm_type == LLMType.DEEPSEEK:
            raise NotImplementedError("DeepSeek API 调用尚未实现")
        else:
            raise ValueError(f"不支持的 LLM 类型: {llm_type}")



