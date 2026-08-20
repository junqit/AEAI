"""
AEBaiduStorage 测试 —— 直接创建 AEBaiduStorage 连百度网盘做真实联网测试。
首次运行若无 bypy 授权 token（~/.bypy/bypy.json），会触发 bypy 交互式授权：
打印授权 URL（用 credentials.py 里的 appkey）→ 浏览器授权 → 粘贴 Authorization Code
→ 缓存 token 到 ~/.bypy/bypy.json → 列出第一层。之后运行即自动连接、列出应用根目录文件。
运行：cd CloudSorage && python ./baidu/test_baidu_storage.py
"""
import os
import sys
import unittest

# 把 CloudSorage 根加入 sys.path，便于直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from baidu.AEBaiduStorage import AEBaiduStorage  # noqa: E402


class TestRealIntegration(unittest.TestCase):
    """真实联网测试：直接创建 AEBaiduStorage 连百度网盘。"""

    def test_list_first_level(self):
        s = AEBaiduStorage()  # 直接创建，真实自动连接
        files = s.list_files("")  # 第一层（应用根目录）
        self.assertIsInstance(files, list)
        print("\n[Real] 第一层文件数:", len(files))
        for f in files:
            tag = "DIR " if f.get("isdir") else "FILE"
            print("  %s %s  size=%s" % (
                tag, f.get("server_filename") or f.get("path"), f.get("size", "")))


if __name__ == "__main__":
    unittest.main()
