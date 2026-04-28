"""
简化后的网络数据模型使用示例 - 展示扁平化数据结构
"""

from AEIQ.Network.Core import (
    AENetReq, AENetReqAction,
    AENetRsp, AENetRspStatus, AENetErrorInfo
)


def example_request():
    """请求示例 - AENetReq 直接包含业务字段"""
    print("=" * 60)
    print("请求示例 (扁平化结构)")
    print("=" * 60)

    # 1. 创建聊天请求 - 字段直接在 AENetReq 中
    chat_req = AENetReq(
        action=AENetReqAction.CHAT,
        content="你好，请帮我查询天气",
        context={"id": "ctx_001"},
        question={"type": "text", "content": "今天天气如何"},
        llm_types=["claude", "gemini"],
        request_id="req_001"
    )
    print("\n1. 聊天请求:")
    print(chat_req.model_dump_json(indent=2))

    # 2. 创建查询请求
    query_req = AENetReq(
        action=AENetReqAction.QUERY,
        content="SELECT * FROM users",
        parameters={"database": "main"},
        request_id="req_002"
    )
    print("\n2. 查询请求:")
    print(query_req.model_dump_json(indent=2))

    # 3. 序列化和反序列化
    print("\n3. 序列化测试:")
    bytes_data = chat_req.to_bytes()
    print(f"   序列化后字节数: {len(bytes_data)}")

    restored_req = AENetReq.from_bytes(bytes_data)
    print(f"   反序列化成功: action={restored_req.action}, content={restored_req.content}")


def example_response():
    """响应示例 - AENetRsp 直接包含 content 和 result"""
    print("\n" + "=" * 60)
    print("响应示例 (扁平化结构)")
    print("=" * 60)

    # 1. 使用构造函数创建成功响应 - 字段直接在 AENetRsp 中
    success_rsp1 = AENetRsp(
        status=AENetRspStatus.SUCCESS,
        content="今天北京天气晴朗",
        result={"temperature": "25°C", "humidity": "60%"},
        request_id="req_001"
    )
    print("\n1. 成功响应（构造函数）:")
    print(success_rsp1.model_dump_json(indent=2))

    # 2. 使用快捷方法创建成功响应
    success_rsp2 = AENetRsp.create_success(
        content="查询成功",
        result={"count": 100, "rows": []},
        request_id="req_002"
    )
    print("\n2. 成功响应（快捷方法）:")
    print(success_rsp2.model_dump_json(indent=2))
    print(f"   is_success: {success_rsp2.is_success}")

    # 3. 使用快捷方法创建错误响应
    error_rsp = AENetRsp.create_error(
        error_code="ERR_DB_001",
        error_message="数据库连接失败",
        error_details={"host": "localhost", "port": 5432},
        request_id="req_003"
    )
    print("\n3. 错误响应（快捷方法）:")
    print(error_rsp.model_dump_json(indent=2))
    print(f"   is_error: {error_rsp.is_error}")

    # 4. 序列化和反序列化
    print("\n4. 序列化测试:")
    bytes_data = success_rsp1.to_bytes()
    print(f"   序列化后字节数: {len(bytes_data)}")

    restored_rsp = AENetRsp.from_bytes(bytes_data)
    print(f"   反序列化成功: status={restored_rsp.status}")
    print(f"   content={restored_rsp.content}")
    print(f"   result={restored_rsp.result}")


def main():
    """主函数"""
    example_request()
    example_response()

    print("\n" + "=" * 60)
    print("✅ 所有示例运行成功!")
    print("=" * 60)


if __name__ == "__main__":
    main()
