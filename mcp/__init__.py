"""
MCP (Model Context Protocol) 模块

提供 MCP 工具的定义、注册和管理功能
"""

from .AEMcp import AEMcp, InputSchema, OutputSchema, AESchema, AEMcpType

__all__ = ['AEMcp', 'InputSchema', 'OutputSchema', 'AESchema', 'AEMcpType']
