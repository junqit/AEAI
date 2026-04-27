"""
更新后的网络数据模型使用示例
"""

from AEIQ.Network.Core import (
    AENetReq, AENetReqAction, AENetReqData,
    AENetRsp, AENetRspStatus, AENetErrorInfo, AENetRspData
)


def example_request():
    """请求示例"""
    print("=" * 60)
    print("请求示例")
    print("=" * 60)

    # 1. 创建聊天请求
    chat_req = AENetReq(
        action=AENetReqAction.CHAT,
        data=AENetReqData(
            content="你好，请帮我查询天气",
            parameters={"location": "北京"}
        ),
        request_id="req_001"
    )
    print("\n1. 聊天请求:")
    print(chat_req.model_dump_json(indent=2))

    # 2. 创建查询请求
    query_req = AENetReq(
        action=AENetReqAction.QUERY,
        data=AENetReqData(
            content="SELECT * FROM users",
            parameters={"database": "main"}
        ),
        request_id="req_002"
    )
    print("\n2. 查询请求:")
    print(query_req.model_dump_json(indent=2))

    # 3. 创建心跳请求
    heartbeat_req = AENetReq(
        action=AENetReqAction.HEARTBEAT,
        request_id="req_003"
    )
    print("\n3. 心跳请求:")
    print(heartbeat_req.model_dump_json(indent=2))

    # 4. 序列化和反序列化
    print("\n4. 序列化测试:")
    bytes_data = chat_req.to_bytes()
    print(f"   序列化后字节数: {len(bytes_data)}")

    # 反序列化（跳过前4字节的长度标记）
    restored_req = AENetReq.from_bytes(bytes_data[4:])
    print(f"   反序列化成功: action={restored_req.action}")


def example_response():
    """响应示例"""
    print("\n" + "=" * 60)
    print("响应示例")
    print("=" * 60)

    # 1. 使用构造函数创建成功响应
    success_rsp1 = AENetRsp(
        status=AENetRspStatus.SUCCESS,
        data=AENetRspData(
            content="今天北京天气晴朗",
            result={"temperature": "25°C", "humidity": "60%"}
        ),
        request_id="req_001"
    )
    print("\n1. 成功响应（构造函数）:")
    print(success_rsp1.model_dump_json(indent=2))

    # 2. 使用快捷方法创建成功响应
    success_rsp2 = AENetRsp.create_success(
        data=AENetRspData(
            content="查询成功",
            result={"count": 100, "rows": []}
        ),
        request_id="req_002"
    )
    print("\n2. 成功响应（快捷方法）:")
    print(success_rsp2.model_dump_json(indent=2))
    print(f"   is_success: {success_rsp2.is_success}")

    # 3. 使用构造函数创建错误响应
    error_rsp1 = AENetRsp(
        status=AENetRspStatus.ERROR,
        error=AENetErrorInfo(
            code="ERR_DB_001",
            message="数据库连接失败",
            details={"host": "localhost", "port": 5432}
        ),
        request_id="req_003"
    )
    print("\n3. 错误响应（构造函数）:")
    print(error_rsp1.model_dump_json(indent=2))

    # 4. 使用快捷方法创建错误响应
    error_rsp2 = AENetRsp.create_error(
        error_code="ERR_AUTH_001",
        error_message="用户未授权",
        error_details={"user": "guest", "required_role": "admin"},
        request_id="req_004"
    )
    print("\n4. 错误响应（快捷方法）:")
    print(error_rsp2.model_dump_json(indent=2))
    print(f"   is_error: {error_rsp2.is_error}")

    # 5. 超时响应
    timeout_rsp = AENetRsp(
        status=AENetRspStatus.TIMEOUT,
        error=AENetErrorInfo(
            code="ERR_TIMEOUT",
            message="请求超时",
            details={"timeout_seconds": 30}
        ),
        request_id="req_005"
    )
    print("\n5. 超时响应:")
    print(timeout_rsp.model_dump_json(indent=2))

    # 6. 处理中响应
    processing_rsp = AENetRsp(
        status=AENetRspStatus.PROCESSING,
        data=AENetRspData(
            content="正在处理您的请求...",
            result={"progress": "50%"}
        ),
        request_id="req_006"
    )
    print("\n6. 处理中响应:")
    print(processing_rsp.model_dump_json(indent=2))

    # 7. 序列化和反序列化
    print("\n7. 序列化测试:")
    bytes_data = success_rsp1.to_bytes()
    print(f"   序列化后字节数: {len(bytes_data)}")

    # 反序列化（跳过前4字节的长度标记）
    restored_rsp = AENetRsp.from_bytes(bytes_data[4:])
    print(f"   反序列化成功: status={restored_rsp.status}")


def example_enum_usage():
    """枚举使用示例"""
    print("\n" + "=" * 60)
    print("枚举使用示例")
    print("=" * 60)

    # 1. 使用枚举创建请求
    req = AENetReq(
        action=AENetReqAction.COMMAND,
        data=AENetReqData(content="ls -la")
    )
    print("\n1. 使用枚举创建请求:")
    print(f"   action 类型: {type(req.action)}")
    print(f"   action 值: {req.action}")

    # 2. 枚举会自动转换为字符串值（因为 use_enum_values = True）
    json_data = req.model_dump()
    print("\n2. 序列化后的数据:")
    print(f"   action 类型: {type(json_data['action'])}")
    print(f"   action 值: {json_data['action']}")

    # 3. 从字符串反序列化
    json_str = '{"action": "query", "data": null, "request_id": null}'
    req_from_json = AENetReq.model_validate_json(json_str)
    print("\n3. 从 JSON 反序列化:")
    print(f"   action: {req_from_json.action}")

    # 4. 所有可用的请求动作
    print("\n4. 所有可用的请求动作:")
    for action in AENetReqAction:
        print(f"   - {action.name}: {action.value}")

    # 5. 所有可用的响应状态
    print("\n5. 所有可用的响应状态:")
    for status in AENetRspStatus:
        print(f"   - {status.name}: {status.value}")


def example_validation():
    """数据验证示例"""
    print("\n" + "=" * 60)
    print("数据验证示例")
    print("=" * 60)

    # 1. 正常创建
    try:
        req = AENetReq(action=AENetReqAction.CHAT)
        print("\n1. 正常创建成功")
    except Exception as e:
        print(f"\n1. 创建失败: {e}")

    # 2. 缺少必填字段
    try:
        req = AENetReq()  # 缺少 action
        print("\n2. 缺少必填字段 - 创建成功（不应该发生）")
    except Exception as e:
        print(f"\n2. 缺少必填字段 - 验证失败（预期）: {type(e).__name__}")

    # 3. 错误的枚举值
    try:
        json_str = '{"action": "invalid_action"}'
        req = AENetReq.model_validate_json(json_str)
        print("\n3. 错误的枚举值 - 创建成功（不应该发生）")
    except Exception as e:
        print(f"\n3. 错误的枚举值 - 验证失败（预期）: {type(e).__name__}")

    # 4. 响应必填字段
    try:
        rsp = AENetRsp(status=AENetRspStatus.SUCCESS)
        print("\n4. 响应创建成功")
    except Exception as e:
        print(f"\n4. 响应创建失败: {e}")


if __name__ == "__main__":
    # 运行所有示例
    example_request()
    example_response()
    example_enum_usage()
    example_validation()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)
