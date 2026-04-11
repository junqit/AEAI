from sentence_transformers import SentenceTransformer
import os

# 设置离线模式
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

# 如果模型已在本地缓存
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')



# from mcp import ClientSession
# from mcp.client.stdio import stdio_client

# # 启动一个 MCP server（比如本地 python server）
# server_params = {
#     "command": "python",
#     "args": ["mcp_server.py"]
# }

# with stdio_client(server_params) as (read, write):
#     with ClientSession(read, write) as session:

#         session.initialize()

#         tools = session.list_tools()

#         print("可用工具：", tools)