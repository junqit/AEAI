"""Excutor 子包：叶子执行角色 Flow。

直继 AERoleBase（不经 AERoleExcutor 编排层），按 _role() 指定角色枚举；
title/responsibility 由 ROLE_PARAMS 拉取，不在子类重定义（元数据单一来源）。
"""
