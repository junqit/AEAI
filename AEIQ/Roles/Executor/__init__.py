"""Executor 子包：直接执行产出类能力 mixin。

含 answer（LLM 推理作答）、execute（脚本执行）——直接产出结果的能力。
作为 mixin 被 AEOrchestrator 继承，在 LLM action 选择后执行。
"""
