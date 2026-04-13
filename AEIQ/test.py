# test.py
import sys
import os
import json
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# model_path = os.path.expanduser(
#                 "~/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
#             )

# model = SentenceTransformer(model_path)


# data = ["multiply or +",
#     "今天天气很好",
#     "什么是生命"
# ]

# embeddings = model.encode(data, normalize_embeddings=True)
# print(f"{data} {embeddings}")

# query = "+"
# q_emb = model.encode([query], normalize_embeddings=True)

# sim = cosine_similarity(q_emb, embeddings)[0]
# print(sim)

# top_k = np.argsort(sim)[::-1][:2]
# results = [data[i] for i in top_k]
# print(top_k)
# print(results)

# from mlx_lm import load, generate

# model, tokenizer = load("/Users/tianjunqi/gemma-mlx")
# messages = [
#     {"role": "system", "content": "把用户的问题做成执行计划，以 json 结构输出"},
#     {"role": "user", "content": "写一个 python 版本的 hello world"}
# ]

# prompt = tokenizer.apply_chat_template(
#     messages,
#     tokenize=False,
#     add_generation_prompt=True
# )

# response = generate(
#     model,
#     tokenizer,
#     prompt=prompt,
#     max_tokens=4096
# )

# print(response)


# import torch
# from transformers import AutoProcessor, AutoModelForCausalLM

# MODEL_ID = "google/gemma-4-26B-A4B-it"

# # Load model
# processor = AutoProcessor.from_pretrained(MODEL_ID)
# model = AutoModelForCausalLM.from_pretrained(
#     MODEL_ID,
#     dtype=torch.float16,
#     device_map="auto"
# )

from huggingface_hub import snapshot_download
import os

def download_model():
    """
    下载 Hugging Face 模型到本地
    
    Args:
        model_name: 模型名称
        local_dir: 本地保存目录
    """
    try:

        model_name = "google/gemma-4-26B-A4B-it"
        local_dir = "/Users/tianjunqi/llms/"

        # 构建完整的本地路径
        model_local_path = os.path.join(local_dir, model_name.split("/")[-1])
        
        print(f"开始下载模型: {model_name}")
        print(f"保存路径: {model_local_path}")
        
        # 下载模型（移除 resume_download 参数）
        model_path = snapshot_download(
            repo_id=model_name,
            local_dir=model_local_path,
            local_files_only=False,
            ignore_patterns=["*.h5", "*.ot", "*.msgpack"]  # 可选：忽略大文件
        )
        
        print(f"✓ 模型下载成功！")
        print(f"  位置: {model_path}")
        return model_path
        
    except Exception as e:
        print(f"✗ 下载失败: {e}")
        return None

# 如果需要设置镜像（国内用户）
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 下载模型
if __name__ == "__main__":
    model_path = download_model()
    
    if model_path:
        print("\n使用方式:")
        print(f"from sentence_transformers import SentenceTransformer")
        print(f"model = SentenceTransformer('{model_path}')")
