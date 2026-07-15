import json
import uuid


class AEExpertAssistant:

    MAIN_STEP_GENERATE_NAME = "generate_name"
    MAIN_STEP_GENERATE_FIELDS = "generate_fields"
    MAIN_STEP_GENERATE_CONTENT = "generate_content"
    MAIN_STEP_ASSEMBLE = "assemble"

    TAG = "AEExpertAssistant"

    def __init__(self):

        self.role = "Expert Assistant Creator"
        self.task_id = f"{self.TAG}_{uuid.uuid4().hex[:8]}"

        self.base_context = """你是一名 AI 组织设计专家。

你正在为用户动态创建一个「专家助理（Expert Assistant）」。

专家助理不是执行者，而是领域专家、评审专家和裁决专家。

其职责是：
1. 理解用户问题
2. 分析问题所属领域
3. 动态构建评价框架
4. 动态生成证据需求
5. 判断证据是否充分
6. 对证据进行专业分析
7. 发现问题与风险
8. 输出裁决结果
9. 生成修复建议或补充证据需求
10. 在证据不足或结果不达标时发起重新评估

禁止：
- 不直接执行任务
- 不直接修改代码
- 不直接收集数据
- 不直接调用工具
- 不代替员工完成工作

专家助理只负责：
- 定义标准
- 定义评价维度
- 定义证据需求
- 分析证据
- 专业判断
- 最终裁决"""

        self.workflow = {
            "main_steps": [
                self.MAIN_STEP_GENERATE_NAME,
                self.MAIN_STEP_GENERATE_FIELDS,
                self.MAIN_STEP_GENERATE_CONTENT,
                self.MAIN_STEP_ASSEMBLE,
            ],
            "current_main_step": None,
            "current_field_index": None,
            "fields": [],
            "generated": {},
            "expert_name": None,
            "user_question": None,
        }

    def start(self, user_question):
        """启动工作流，返回第一步的 prompt"""
        self.workflow["user_question"] = user_question
        self.workflow["current_main_step"] = self.MAIN_STEP_GENERATE_NAME
        return self._build_current_prompt()

    def receive(self, llm_raw_output):
        """
        接收 LLM 原始输出，解析并校验 task_id 归属，推进工作流。
        返回: 下一步 prompt(str) 或最终 JSON(str)。
        若 task_id 不匹配返回 None。
        """
        parsed = self._parse_llm_output(llm_raw_output)
        if parsed is None:
            return None
        if parsed["task_id"] != self.task_id:
            return None

        content = parsed["content"]
        step = self.workflow["current_main_step"]

        if step == self.MAIN_STEP_GENERATE_NAME:
            self.workflow["expert_name"] = content.strip() if isinstance(content, str) else str(content)
            self.workflow["current_main_step"] = self.MAIN_STEP_GENERATE_FIELDS

        elif step == self.MAIN_STEP_GENERATE_FIELDS:
            self.workflow["fields"] = content if isinstance(content, list) else json.loads(content)
            self.workflow["current_main_step"] = self.MAIN_STEP_GENERATE_CONTENT
            self.workflow["current_field_index"] = 0

        elif step == self.MAIN_STEP_GENERATE_CONTENT:
            field = self.workflow["fields"][self.workflow["current_field_index"]]
            self.workflow["generated"][field["key"]] = content
            self.workflow["current_field_index"] += 1

            if self.workflow["current_field_index"] >= len(self.workflow["fields"]):
                self.workflow["current_main_step"] = self.MAIN_STEP_ASSEMBLE
                return self._finish()

        return self._build_current_prompt()

    def get_status(self):
        """返回当前工作流状态"""
        step = self.workflow["current_main_step"]
        total_main = len(self.workflow["main_steps"])
        main_index = self.workflow["main_steps"].index(step) if step else 0

        status = {
            "task_id": self.task_id,
            "main_step": f"[{main_index + 1}/{total_main}] {step}",
            "expert_name": self.workflow["expert_name"],
        }

        if step == self.MAIN_STEP_GENERATE_CONTENT:
            field_index = self.workflow["current_field_index"]
            total_fields = len(self.workflow["fields"])
            current_field = self.workflow["fields"][field_index] if field_index < total_fields else None
            status["field_progress"] = f"[{field_index + 1}/{total_fields}]"
            status["current_field"] = current_field["key"] if current_field else "done"
            status["generated_so_far"] = self.workflow["generated"]

        return status

    def _build_current_prompt(self):
        """根据当前步骤构建完整 prompt，包含输出结构要求"""
        step = self.workflow["current_main_step"]
        question = self.workflow["user_question"]
        name = self.workflow["expert_name"]

        if step == self.MAIN_STEP_GENERATE_NAME:
            return self._prompt_generate_name(question)
        elif step == self.MAIN_STEP_GENERATE_FIELDS:
            return self._prompt_generate_fields(question, name)
        elif step == self.MAIN_STEP_GENERATE_CONTENT:
            field = self.workflow["fields"][self.workflow["current_field_index"]]
            return self._prompt_generate_field_content(question, name, field, self.workflow["generated"])
        return None

    def _finish(self):
        """组装最终 JSON 并返回"""
        result = {"name": self.workflow["expert_name"]}
        for field in self.workflow["fields"]:
            result[field["key"]] = self.workflow["generated"].get(field["key"], None)

        final_json = json.dumps(result, ensure_ascii=False, indent=2)
        print(f"\n{'='*60}")
        print(f"[{self.task_id}] Expert Assistant Created: {self.workflow['expert_name']}")
        print(f"{'='*60}")
        print(final_json)
        print(f"{'='*60}\n")
        return final_json

    def _parse_llm_output(self, raw_output):
        """解析 LLM 输出，提取 task_id 和 content"""
        raw_output = raw_output.strip()
        try:
            parsed = json.loads(raw_output)
            if isinstance(parsed, dict) and "task_id" in parsed and "content" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        return None

    # ---- Prompt 构建：每个 prompt 都包含完整的输出结构示例 ----

    def _prompt_generate_name(self, user_question):
        example = json.dumps({
            "task_id": self.task_id,
            "content": "AECodeReviewer"
        }, ensure_ascii=False, indent=2)

        parts = [
            f"[Role]: {self.role}",
            f"[Background]:\n{self.base_context}",
            f"[User Question]: {user_question}",
            f"""[Instruction]:
根据用户的问题，为需要创建的专家助理命名。

要求：
- AE 开头，驼峰命名
- 名称体现该专家的专业领域
- 如 AECodeReviewer、AESecurityAuditor、AEArchitectAdvisor""",
            f"""[Output Structure]:
你必须严格按以下 JSON 结构输出，不要输出任何 JSON 之外的文字：

{example}

其中 task_id 必须原样保留为 "{self.task_id}"，content 替换为你生成的专家名称字符串。""",
        ]
        return "\n\n".join(parts)

    def _prompt_generate_fields(self, user_question, expert_name):
        example = json.dumps({
            "task_id": self.task_id,
            "content": [
                {"key": "domain", "description": "所属专业领域", "value_type": "string"},
                {"key": "role", "description": "角色定位描述", "value_type": "string"},
                {"key": "expertise", "description": "核心专业能力", "value_type": "array"},
            ]
        }, ensure_ascii=False, indent=2)

        parts = [
            f"[Role]: {self.role}",
            f"[Background]:\n{self.base_context}",
            f"[User Question]: {user_question}",
            f"[Expert Name]: {expert_name}",
            f"""[Instruction]:
根据用户的问题和专家名称，分析该专家助理需要哪些属性字段。

每个字段包含：
- key: 字段名（英文，snake_case）
- description: 该字段的含义说明
- value_type: 值类型（string / array / object）

请根据问题的领域特性动态决定字段，例如：
- 评审类 → evaluation_workflow、judgment_rules、evidence_requirements
- 风险类 → risk_assessment_rules、risk_levels、mitigation_strategy
- 创作类 → quality_criteria、style_guidelines、review_dimensions
- 决策类 → decision_framework、tradeoff_rules、constraints""",
            f"""[Output Structure]:
你必须严格按以下 JSON 结构输出，不要输出任何 JSON 之外的文字：

{example}

其中 task_id 必须原样保留为 "{self.task_id}"，content 替换为你生成的字段数组。""",
        ]
        return "\n\n".join(parts)

    def _prompt_generate_field_content(self, user_question, expert_name, field, generated_so_far):
        value_type = field["value_type"]
        content_example = {
            "string": "这里是字符串内容",
            "array": ["项目1", "项目2", "项目3"],
            "object": {"key1": "value1", "key2": "value2"},
        }
        example = json.dumps({
            "task_id": self.task_id,
            "content": content_example.get(value_type, "")
        }, ensure_ascii=False, indent=2)

        parts = [
            f"[Role]: {self.role}",
            f"[Background]:\n{self.base_context}",
            f"[User Question]: {user_question}",
            f"[Expert Name]: {expert_name}",
        ]

        if generated_so_far:
            parts.append(f"[Already Generated]:\n{json.dumps(generated_so_far, ensure_ascii=False, indent=2)}")

        parts.append(f"[Current Field]: \"{field['key']}\" — {field['description']}")
        parts.append(f"[Value Type]: {value_type}")
        parts.append(f"[Instruction]: 根据用户问题和已有上下文，生成该字段的内容。")
        parts.append(f"""[Output Structure]:
你必须严格按以下 JSON 结构输出，不要输出任何 JSON 之外的文字：

{example}

其中 task_id 必须原样保留为 "{self.task_id}"，content 替换为你生成的 {value_type} 类型的实际内容。""")

        return "\n\n".join(parts)
