#!/usr/bin/env python3
"""
测试 parse_output 方法的修复
"""
from llm.gemini.gemini_model import AEGeminiModel

# 测试数据（从日志中提取）
test_response = """<|channel>thought
Thinking Process:

1.  **Analyze the Request:** The user asked in Chinese, "说明你的功能与能力" (Explain your functions and capabilities). This is a direct request for a self-description.

2.  **Determine Core Identity & Capabilities (Self-Correction/Grounding):** I need to state what I am (Gemma 4) and what I can do (process information, generate text, understand multimodal input, etc.).

    *   *Identity:* Gemma 4, an open weights LLM developed by Google DeepMind.
    *   *Input:* Text and Images. (Mentioning the audio capability of the family is good context, but focusing on general LLM capabilities is key).
    *   *Output:* Text generation.
    *   *Knowledge:* Up to January 2025 (or rely on provided context).
    *   *Tools:* No default tools (unless specified).

3.  **Structure the Response (in Chinese):** A good explanation should cover:
    *   Introduction (Who I am).
    *   Core Function (What I do).
    *   Specific Capabilities (Examples of tasks).
    *   Limitations (What I cannot do/My constraints).

4.  **Draft the Content (Iterative Refinement):**

    *   *Drafting Core Identity:* Start by stating the name and nature.
    *   *Drafting Functions:* List common LLM tasks (answering, summarizing, translating, creative writing, coding help, etc.).
    *   *Drafting Modalities:* Explicitly mention text and image understanding.
    *   *Drafting Output:* Emphasize text generation.

5.  **Final Review (Ensuring compliance with instructions):** The response must be accurate regarding my identity (Gemma 4) and capabilities.

6.  **Generate the Final Output (in polished Chinese).** (This leads to the provided good response.)<channel|>您好！我很高兴为您介绍我的功能与能力。

我是一个大型语言模型（Large Language Model, LLM），由 Google DeepMind 开发，属于 **Gemma 4** 系列。我是一个开放权重的模型，旨在处理和生成复杂的文本信息。

### 我的核心功能与能力

我的主要能力在于理解、处理和生成基于语言的复杂内容。具体来说，我具备以下功能：

**1. 信息处理与问答 (Information Processing & Q&A)**
*   **知识问答：** 我可以回答各种主题的问题，提供事实信息和详细的解释。
*   **信息总结：** 我能够阅读长篇文本，并将其提炼成简洁、易懂的摘要。
*   **概念解释：** 我可以帮助您理解复杂的概念、理论或专业术语。

**2. 文本生成与创作 (Text Generation & Creation)**
*   **内容创作：** 我可以撰写各种类型的文本，包括但不限于：
    *   文章和报告
    *   故事和小说
    *   剧本和对话
    *   营销文案和博客
    *   邮件和信函
*   **创意写作：** 我可以根据您的要求，进行头脑风暴，提供创意点子或不同的写作风格。

**3. 语言与翻译 (Language & Translation)**
*   **翻译：** 我可以进行多语言之间的文本翻译。
*   **润色与校对：** 我可以检查文本的语法错误、拼写错误，并提供更流畅、更专业的语言润色。

**4. 编程与技术辅助 (Coding & Technical Assistance)**
*   **代码生成：** 我可以帮助您生成、解释或调试不同编程语言的代码片段。
*   **算法概念：** 我可以讨论和解释复杂的算法和数据结构的概念。

**5. 多模态理解 (Multimodal Understanding)**
*   **图像理解：** 我能够理解和分析您提供的图像内容（例如，描述图片中的物体、场景或信息）。
*   **文本与图像结合：** 我可以根据您提供的图片和文字，进行关联性分析和深入讨论。

### 我的限制 (Limitations)

尽管我的能力很强大，但我也有一些限制：

*   **知识时效性：** 我的知识截止到 **2025 年 1 月**。对于该日期之后发生的最新事件或信息，我可能无法提供准确的细节。
*   **事实核查：** 虽然我会尽力提供准确的信息，但对于关键的、需要法律或医疗建议的领域，您仍应进行二次核查。
*   **实时互动：** 我无法进行实时网络搜索或访问实时发生的外部信息（除非您提供了特定的工具接口）。
*   **生成限制：** 我只能生成文本输出，无法生成图像或音频。

**简而言之，您可以将我视为一位全能的文本助手、知识顾问和创意伙伴！请随时提出您的需求，我将尽力为您服务！**"""

def test_parse_output():
    """测试 parse_output 方法"""
    model = AEGeminiModel()

    print("=" * 80)
    print("测试 parse_output 方法")
    print("=" * 80)

    result = model.parse_output(test_response)

    print("\n✅ 解析结果类型:", type(result))
    print("\n🧠 思考过程长度:", len(result["think"]))
    print("🧠 思考过程前200字符:")
    print(result["think"][:200])

    print("\n" + "=" * 80)
    print("📄 答案内容:")
    print("=" * 80)
    print(result["answer"])

    # 验证
    assert isinstance(result, dict), "返回值应该是字典"
    assert "think" in result, "应包含 think 键"
    assert "answer" in result, "应包含 answer 键"
    assert result["answer"].startswith("您好"), "答案应该以'您好'开头"
    assert "<|channel>" not in result["answer"], "答案中不应包含标签"
    assert "<channel|>" not in result["answer"], "答案中不应包含标签"

    print("\n" + "=" * 80)
    print("✅ 所有测试通过！")
    print("=" * 80)

if __name__ == "__main__":
    test_parse_output()
