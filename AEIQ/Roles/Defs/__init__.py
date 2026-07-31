"""Defs 子包：角色定义类（继承 AERoleBase）。

每个角色一个类，仅通过 _role() 指定角色枚举；title/responsibility 由 AERoleType.ROLE_PARAMS
拉取，不在子类重定义（元数据单一来源）。

- expert   : AEExpertRole
- workgroup: AEWorkgroupRole
- employee : AEEmployeeRole
- task     : AETaskRole（原子任务执行，_role()=task）
- llm      : AELLMRole（LLM 直接作答 flow，亦在此包内）
- refiner  : AERefiner（问题精炼 flow，继承 AERoleExcutor，亦在此包内）

AERoleExcutor（本包）为上述角色类的基类，提供执行/角色选择能力与 _role()=task 默认。
"""
