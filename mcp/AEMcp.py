"""
AEMcp - MCP 工具基础类

简化版本：inputSchema 和 outSchema 各自用子类实现
"""

from typing import Dict, Any, Optional, Callable
from enum import Enum


class AEMcpType(str, Enum):
    """MCP 工具类型"""
    CALCULATION = "calculation"
    QUERY = "query"
    ACTION = "action"
    TRANSFORMATION = "transformation"


class AESchema:
    """Schema 基础类"""

    def __init__(self, properties: Dict[str, Any], required: list = None):
        """
        初始化 Schema

        Args:
            properties: 字段属性定义
            required: 必需字段列表
        """
        self.properties = properties
        self.required = required or []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "type": "object",
            "properties": self.properties
        }
        if self.required:
            result["required"] = self.required
        return result

    def __repr__(self):
        return f"{self.__class__.__name__}(properties={self.properties})"


class InputSchema(AESchema):
    """输入参数 Schema"""
    pass


class OutputSchema(AESchema):
    """输出结果 Schema"""
    pass


class AEMcp:
    """
    MCP 工具基础类

    Attributes:
        name: 工具名称
        description: 工具描述
        mcp_type: 工具类型
        inputSchema: 输入参数规范
        outSchema: 输出结果规范
        func: 执行函数
    """

    def __init__(
        self,
        name: str,
        description: str,
        inputSchema: InputSchema,
        outSchema: OutputSchema,
        mcp_type: AEMcpType = AEMcpType.ACTION,
        func: Optional[Callable] = None
    ):
        self.name = name
        self.description = description
        self.mcp_type = mcp_type
        self.inputSchema = inputSchema
        self.outSchema = outSchema
        self.func = func

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        if self.func is None:
            raise NotImplementedError(f"工具 {self.name} 未实现执行函数")

        try:
            return self.func(**input_data)
        except Exception as e:
            return {"error": str(e)}

    def to_llm_schema(self) -> Dict[str, Any]:
        """转换为 LLM Schema 格式（用于工具选择）"""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.mcp_type.value,
            "input_schema": self.inputSchema.to_dict()
        }

    def __repr__(self):
        return f"AEMcp(name='{self.name}', type='{self.mcp_type.value}')"


# 示例
if __name__ == "__main__":
    # 创建输入 Schema
    input_schema = InputSchema(
        properties={
            "a": {"type": "integer", "description": "第一个数"},
            "b": {"type": "integer", "description": "第二个数"}
        },
        required=["a", "b"]
    )

    # 创建输出 Schema
    output_schema = OutputSchema(
        properties={
            "result": {"type": "integer", "description": "计算结果"}
        }
    )

    # 创建工具
    add_tool = AEMcp(
        name="add",
        description="计算两个数的和",
        inputSchema=input_schema,
        outSchema=output_schema,
        mcp_type=AEMcpType.CALCULATION,
        func=lambda a, b: {"result": a + b}
    )

    # 测试
    print("工具:", add_tool)
    print("\nLLM Schema:")
    import json
    print(json.dumps(add_tool.to_llm_schema(), indent=2, ensure_ascii=False))

    print("\n执行测试:")
    result = add_tool.execute({"a": 10, "b": 20})
    print(f"add(10, 20) = {result}")
