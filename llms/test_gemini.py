"""
测试 Gemini 模型的加载和使用
按照 AEIQ/test.py 的方式进行测试
"""
from llm.gemini.gemini_model import get_gemini_model


def test_gemini_basic():
    """测试基本的 Gemini 模型加载和生成"""
    print("=" * 60)
    print("测试 1: 基本模型加载和生成")
    print("=" * 60)

    # 1. 获取模型实例
    model = get_gemini_model()

    # 2. 加载模型
    model.load()

    # 3. 准备 messages
    messages = [
        {"role": "system", "content": "把用户的问题做成执行计划，以 json 结构输出"},
        {"role": "user", "content": "写一个 python 版本的 hello world"}
    ]

    # 4. 生成响应
    print("\n开始生成...")
    response = model.generate(
        messages=messages,
        max_tokens=4096
    )

    print(f"\n✅ 生成成功!")
    print(f"响应内容:\n{response}")


def test_gemini_without_system():
    """测试不带 system 提示词的生成"""
    print("\n" + "=" * 60)
    print("测试 2: 不带 system 提示词")
    print("=" * 60)

    model = get_gemini_model()

    messages = [
        {"role": "user", "content": "什么是 Python？"}
    ]

    print("\n开始生成...")
    response = model.generate(
        messages=messages,
        max_tokens=1024
    )

    print(f"\n✅ 生成成功!")
    print(f"响应内容:\n{response[:300]}...")


def test_gemini_multi_turn():
    """测试多轮对话"""
    print("\n" + "=" * 60)
    print("测试 3: 多轮对话")
    print("=" * 60)

    model = get_gemini_model()

    messages = [
        {"role": "user", "content": "什么是 Python？"},
        {"role": "assistant", "content": "Python 是一种高级编程语言。"},
        {"role": "user", "content": "它有什么特点？"}
    ]

    print("\n开始生成...")
    response = model.generate(
        messages=messages,
        max_tokens=1024
    )

    print(f"\n✅ 生成成功!")
    print(f"响应内容:\n{response[:300]}...")


def test_gemini_status():
    """测试获取模型状态"""
    print("\n" + "=" * 60)
    print("测试 4: 获取模型状态")
    print("=" * 60)

    model = get_gemini_model()

    status_before = model.get_status()
    print(f"\n加载前状态: {status_before}")

    model.load()

    status_after = model.get_status()
    print(f"加载后状态: {status_after}")


def main():
    """运行所有测试"""
    print("\n🚀 开始测试 Gemini 模型")
    print("=" * 60)

    try:
        test_gemini_basic()
        # test_gemini_without_system()
        # test_gemini_multi_turn()
        test_gemini_status()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
