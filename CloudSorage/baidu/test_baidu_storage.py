"""
AEBaiduStorage 测试 —— 直连百度网盘 OpenAPI 做真实联网测试。

访问流程（对齐 pythonsdk_20220616 OpenAPI）：
  - 构造零参、非交互：从 ~/.baidu_pan/token.json 加载 access_token，过期用 refresh_token
    自动续期。
  - 若无缓存 token（首次使用），调用 authorize() 走 device-code 授权：
        打印验证 URL/二维码 → 浏览器授权 → 轮询拿 token → 缓存到 ~/.baidu_pan/token.json。
  - 之后列出网盘第一层 + 打印授权用户信息。

运行：cd CloudSorage && python ./baidu/test_baidu_storage.py
首次运行会触发交互式 device-code 授权；之后运行即自动连接、列出第一层。
appkey/secretkey/app_name 从 credentials.py 读取（不读环境变量）。
"""
import os
import sys
import unittest

# 把 CloudSorage 根加入 sys.path，便于直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from baidu.AEBaiduStorage import AEBaiduStorage  # noqa: E402


class TestRealIntegration(unittest.TestCase):
    """真实联网测试：直连百度网盘 OpenAPI。"""

    def test_auth_and_list_first_level(self):
        s = AEBaiduStorage()  # 非交互构造：加载/续期缓存 token
        if not s.is_loaded:
            s.authorize()  # 首次使用：交互式 device-code 授权
        self.assertTrue(s.is_loaded)

        uinfo = s.get_user_info()
        print("\n[Real] 授权用户: %s (uk=%s) errno=%s" % (
            uinfo.get("baidu_name") or uinfo.get("netdisk_name"),
            uinfo.get("uk"), uinfo.get("errno")))

        files = s.list_files("")  # 第一层（沙箱根 /apps/FileManager/，受 credentials.BASE_PATH 影响）
        self.assertIsInstance(files, list)
        print("[Real] 第一层文件数:", len(files))
        for f in files:
            tag = "DIR " if f.get("isdir") else "FILE"
            print("  %s %s  size=%s" % (
                tag, f.get("server_filename") or f.get("path"), f.get("size", "")))


if __name__ == "__main__":
    unittest.main()
