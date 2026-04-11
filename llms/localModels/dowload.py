from huggingface_hub import snapshot_download
import os

def download_model(model_name="sentence-transformers/all-MiniLM-L6-v2", local_dir="./models"):
    """
    下载 Hugging Face 模型到本地
    
    Args:
        model_name: 模型名称
        local_dir: 本地保存目录
    """
    try:
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