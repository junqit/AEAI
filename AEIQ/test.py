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

from mlx_lm import load, generate

model, tokenizer = load("/Users/tianjunqi/gemma-mlx")
messages = [
    {"role": "system", "content": "把用户的问题做成执行计划，以 json 结构输出"},
    {"role": "user", "content": "写一个 python 版本的 hello world"}
]

prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)

response = generate(
    model,
    tokenizer,
    prompt=prompt,
    max_tokens=4096
)

print(response)
