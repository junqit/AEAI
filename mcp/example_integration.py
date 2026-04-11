"""
示例: AEMcp 使用示例
"""

import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from mcp.AEMcp import AEMcp, InputSchema, OutputSchema, AEMcpType
import json


def create_add_tool():
    """创建加法工具"""
    input_schema = InputSchema(
        properties={
            "a": {"type": "integer", "description": "第一个数"},
            "b": {"type": "integer", "description": "第二个数"}
        },
        required=["a", "b"]
    )

    output_schema = OutputSchema(
        properties={
            "result": {"type": "integer", "description": "计算结果"}
        }
    )

    return AEMcp(
        name="add",
        description="计算两个数的和",
        inputSchema=input_schema,
        outSchema=output_schema,
        mcp_type=AEMcpType.CALCULATION,
        func=lambda a, b: {"result": a + b}
    )


def create_multiply_tool():
    """创建乘法工具"""
    input_schema = InputSchema(
        properties={
            "x": {"type": "number", "description": "第一个数"},
            "y": {"type": "number", "description": "第二个数"}
        },
        required=["x", "y"]
    )

    output_schema = OutputSchema(
        properties={
            "result": {"type": "number", "description": "乘积结果"}
        }
    )

    return AEMcp(
        name="multiply",
        description="计算两个数的乘积",
        inputSchema=input_schema,
        outSchema=output_schema,
        mcp_type=AEMcpType.CALCULATION,
        func=lambda x, y: {"result": x * y}
    )


def create_uppercase_tool():
    """创建大写转换工具"""
    input_schema = InputSchema(
        properties={
            "text": {"type": "string", "description": "要转换的文本"}
        },
        required=["text"]
    )

    output_schema = OutputSchema(
        properties={
            "result": {"type": "string", "description": "转换后的大写文本"}
        }
    )

    return AEMcp(
        name="to_uppercase",
        description="将字符串转换为大写",
        inputSchema=input_schema,
        outSchema=output_schema,
        mcp_type=AEMcpType.TRANSFORMATION,
        func=lambda text: {"result": text.upper()}
    )


if __name__ == "__main__":
    print("=" * 60)
    print("AEMcp 使用示例")
    print("=" * 60)

    # 创建工具
    tools = [
        create_add_tool(),
        create_multiply_tool(),
        create_uppercase_tool()
    ]

    for tool in tools:
        print(f"\n📦 工具: {tool.name}")
        print(f"   类型: {tool.mcp_type.value}")
        print(f"   描述: {tool.description}")

        # LLM Schema
        print(f"\n   LLM Schema:")
        print(f"   {json.dumps(tool.to_llm_schema(), ensure_ascii=False)}")

        # 测试执行
        if tool.name == "add":
            result = tool.execute({"a": 10, "b": 20})
            print(f"\n   测试: add(10, 20) = {result}")
        elif tool.name == "multiply":
            result = tool.execute({"x": 5, "y": 6})
            print(f"   测试: multiply(5, 6) = {result}")
        elif tool.name == "to_uppercase":
            result = tool.execute({"text": "hello"})
            print(f"   测试: to_uppercase('hello') = {result}")

    print("\n" + "=" * 60)
