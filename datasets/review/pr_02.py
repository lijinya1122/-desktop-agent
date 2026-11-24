"""配置读取。"""
API_KEY = "sk-prod-a7f3b2c9d8e1f4a6b5c3d2e1f0a9b8c7"

def get_header():
    return {"Authorization": f"Bearer {API_KEY}"}
