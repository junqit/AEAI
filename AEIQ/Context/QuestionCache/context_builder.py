"""
上下文构建器 - 从缓存构建LLM调用的上下文
"""
from typing import List, Dict, Any, Optional
from .cache_store import QuestionCacheStore
from .cache_entry import MessageRole


class ContextBuilder:
    """上下文构建器"""

    def __init__(self, cache_store: QuestionCacheStore):
        """
        初始化上下文构建器

        Args:
            cache_store: 缓存存储实例
        """
        self.cache_store = cache_store

    def build_context(
        self,
        session_id: str,
        max_turns: Optional[int] = None,
        max_tokens: Optional[int] = None,
        include_system_prompt: bool = True,
        system_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        为LLM调用构建上下文消息列表

        Args:
            session_id: 会话ID
            max_turns: 最大对话轮数（从最新往前）
            max_tokens: 最大token数量（粗略估算，1 token ≈ 1.5个字符）
            include_system_prompt: 是否包含系统提示
            system_prompt: 自定义系统提示，如果为None则使用默认

        Returns:
            标准消息格式列表 [{"role": "user/assistant", "content": "..."}, ...]
        """
        messages = []

        # 1. 添加系统提示（如果需要）
        if include_system_prompt:
            prompt = system_prompt or self._get_default_system_prompt()
            messages.append({
                "role": "system",
                "content": prompt
            })

        # 2. 获取历史对话
        turns = self.cache_store.get_conversation_turns(session_id)

        # 3. 应用轮数限制
        if max_turns and len(turns) > max_turns:
            turns = turns[-max_turns:]

        # 4. 转换为消息格式
        for turn in turns:
            # 添加用户问题
            messages.append(turn.question.to_message_format())

            # 添加助手回复（如果有多个LLM回复，选择第一个）
            if turn.responses:
                # 优先使用第一个成功的回复
                response = turn.responses[0]
                messages.append(response.to_message_format())

        # 5. 应用token限制（如果指定）
        if max_tokens:
            messages = self._apply_token_limit(messages, max_tokens)

        return messages

    def build_context_with_llm_selection(
        self,
        session_id: str,
        preferred_llm: str,
        max_turns: Optional[int] = None,
        include_system_prompt: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建上下文，优先选择特定LLM的回复

        Args:
            session_id: 会话ID
            preferred_llm: 优先使用的LLM类型
            max_turns: 最大对话轮数
            include_system_prompt: 是否包含系统提示

        Returns:
            消息列表
        """
        messages = []

        if include_system_prompt:
            messages.append({
                "role": "system",
                "content": self._get_default_system_prompt()
            })

        turns = self.cache_store.get_conversation_turns(session_id)

        if max_turns and len(turns) > max_turns:
            turns = turns[-max_turns:]

        for turn in turns:
            messages.append(turn.question.to_message_format())

            # 查找指定LLM的回复
            preferred_response = None
            for response in turn.responses:
                if response.llm_type == preferred_llm:
                    preferred_response = response
                    break

            # 如果没找到，使用第一个回复
            if preferred_response is None and turn.responses:
                preferred_response = turn.responses[0]

            if preferred_response:
                messages.append(preferred_response.to_message_format())

        return messages

    def build_summary_context(
        self,
        session_id: str,
        summarize_old_turns: int = 10
    ) -> List[Dict[str, str]]:
        """
        构建带摘要的上下文（将旧对话摘要化以节省token）

        Args:
            session_id: 会话ID
            summarize_old_turns: 超过这个数量的旧对话将被摘要

        Returns:
            消息列表（包含摘要）
        """
        turns = self.cache_store.get_conversation_turns(session_id)

        if len(turns) <= summarize_old_turns:
            # 不需要摘要，直接返回完整上下文
            return self.build_context(session_id)

        messages = [
            {
                "role": "system",
                "content": self._get_default_system_prompt()
            }
        ]

        # 摘要旧对话
        old_turns = turns[:-summarize_old_turns]
        summary = self._summarize_turns(old_turns)
        if summary:
            messages.append({
                "role": "system",
                "content": f"历史对话摘要：\n{summary}"
            })

        # 添加最近的完整对话
        recent_turns = turns[-summarize_old_turns:]
        for turn in recent_turns:
            messages.append(turn.question.to_message_format())
            if turn.responses:
                messages.append(turn.responses[0].to_message_format())

        return messages

    def get_context_stats(self, session_id: str) -> Dict[str, Any]:
        """
        获取上下文统计信息

        Args:
            session_id: 会话ID

        Returns:
            统计信息
        """
        turns = self.cache_store.get_conversation_turns(session_id)
        entries = self.cache_store.get_session_history(session_id)

        total_chars = sum(len(e.content) for e in entries)
        estimated_tokens = int(total_chars / 1.5)  # 粗略估算

        return {
            "session_id": session_id,
            "total_turns": len(turns),
            "total_entries": len(entries),
            "total_characters": total_chars,
            "estimated_tokens": estimated_tokens
        }

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示"""
        return (
            "你是一个helpful的AI助手。"
            "请根据对话历史和用户的问题，提供准确、有帮助的回答。"
        )

    def _apply_token_limit(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int
    ) -> List[Dict[str, str]]:
        """
        应用token限制，从最新的消息开始保留

        Args:
            messages: 消息列表
            max_tokens: 最大token数

        Returns:
            裁剪后的消息列表
        """
        # 粗略估算：1 token ≈ 1.5 字符
        estimated_tokens = 0
        result = []

        # 保留系统提示
        if messages and messages[0].get("role") == "system":
            result.append(messages[0])
            estimated_tokens += len(messages[0]["content"]) / 1.5
            messages = messages[1:]

        # 从最新的消息开始添加
        for msg in reversed(messages):
            msg_tokens = len(msg["content"]) / 1.5
            if estimated_tokens + msg_tokens <= max_tokens:
                result.insert(1 if result and result[0]["role"] == "system" else 0, msg)
                estimated_tokens += msg_tokens
            else:
                break

        return result

    def _summarize_turns(self, turns: List) -> str:
        """
        摘要化对话轮次

        Args:
            turns: 对话轮次列表

        Returns:
            摘要文本
        """
        if not turns:
            return ""

        summaries = []
        for i, turn in enumerate(turns, 1):
            q_preview = turn.question.content[:50]
            if len(turn.question.content) > 50:
                q_preview += "..."

            r_preview = ""
            if turn.responses:
                r_preview = turn.responses[0].content[:50]
                if len(turn.responses[0].content) > 50:
                    r_preview += "..."

            summaries.append(f"{i}. Q: {q_preview}\n   A: {r_preview}")

        return "\n".join(summaries)
