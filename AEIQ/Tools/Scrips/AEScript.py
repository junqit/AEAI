"""
AEScript - 脚本的接口定义（Protocol）
每个脚本声明自己的 input_schema、output_schema、脚本内容和执行类型
执行由 Runner 完成，脚本本身不负责执行
"""
from typing import Dict, Any, Protocol, runtime_checkable


@runtime_checkable
class AEScript(Protocol):
    """脚本接口协议"""

    script_id: str
    name: str
    description: str
    runner: str  # "zsh" | "python" | "ruby"
    content: str  # 脚本内容或文件路径
    input_schema: dict
    output_schema: dict
