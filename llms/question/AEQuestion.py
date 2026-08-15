from dataclasses import dataclass
from typing import List, Dict, Any
from common.aellm_enums import AELLMType, AEAiLevel  # noqa: F401  (re-export)


@dataclass
class AEQuestion:
    messages: List[Dict[str, Any]]
    llm_type: AELLMType
    level: AEAiLevel = AEAiLevel.default
    # 流式生成过程中累计拼接的内容
    think_content: str = ""   # 思考内容（thinking_delta 累计拼接）
    delta_content: str = ""   # 回答内容（text_delta 累计拼接，即最终结果）

    def append_think(self, text: str) -> None:
        """拼接思考内容片段（thinking_delta 增量）。"""
        if text:
            self.think_content += text

    def append_delta(self, text: str) -> None:
        """拼接回答内容片段（text_delta 增量，即最终结果）。"""
        if text:
            self.delta_content += text

    def feed_think(self, info: Dict[str, Any]) -> None:
        """
        由 think_process 回调调用：从进度信息中提取增量思考内容拼接进 think_content。

        info['content'] 为模型侧已拼接的「累计思考内容」（随流式单调前缀增长），
        此处取相对已拼接部分的增量片段，避免重复拼接。
        """
        cumulative = info.get("content", "") if isinstance(info, dict) else ""
        prev = self.think_content
        piece = cumulative[len(prev):] if cumulative.startswith(prev) else cumulative
        self.append_think(piece)

    def feed_delta(self, info: Dict[str, Any]) -> None:
        """
        由 delta_process 回调调用：从进度信息中提取增量回答内容拼接进 delta_content。

        info['content'] 为模型侧已拼接的「累计回答内容」（随流式单调前缀增长），
        此处取相对已拼接部分的增量片段，避免重复拼接。
        """
        cumulative = info.get("content", "") if isinstance(info, dict) else ""
        prev = self.delta_content
        piece = cumulative[len(prev):] if cumulative.startswith(prev) else cumulative
        self.append_delta(piece)

    def reset_stream_content(self) -> None:
        """重置累计拼接的 think/delta 内容（复用同一 question 重新生成前调用）。"""
        self.think_content = ""
        self.delta_content = ""
