"""AENetReq 数据格式示例 - 精简版"""

from AEIQ.Network.Core import AENetReq, AENetRsp
import json


def example_clean_format():
    """展示简化后的 AENetReq 格式"""
    print("=" * 80)
    print("AENetReq 精简格式")
    print("=" * 80)

    # 创建请求
    req = AENetReq(
        action="chat",
        context={"id": "ctx_1b4bf8d8f4f34424"},
        requestId="582145C8-2EAE-4908-BAFF-DA3B24A68798",
        question={"type": "text", "content": "adf莾奈斯地"},
        llm_types=["claude", "gemini"],
        timeout=1000.0,
        path="/ae/context/chat"
    )

    print("\n请求对象:")
    print(req.model_dump_json(exclude_none=True, indent=2, by_alias=True))

    # 创建响应
    rsp = AENetRsp.create_success(
        content="处理成功",
        result={"data": "result"},
        request_id=req.requestId
    )

    print("\n响应对象:")
    print(rsp.model_dump_json(exclude_none=True, indent=2))


if __name__ == "__main__":
    example_clean_format()

