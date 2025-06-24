import requests
import json
from config import LOCAL_LLM_URL

def local_chat(prompt_messages):
    url = LOCAL_LLM_URL
    headers = {"Content-Type": "application/json"}

    data = {
        "model": "local-model",  # hoặc bỏ luôn
        "messages": prompt_messages,
        "temperature": 0.7,
        "stream": False
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        res_json = response.json()
        print("✅ RES:", res_json)

        # Check format
        if "choices" in res_json:
            return res_json["choices"][0]["message"]["content"]
        elif "text" in res_json:
            return res_json["text"]
        else:
            return "[LỖI]: Không tìm thấy phản hồi từ local model"

    except Exception as e:
        print("❌ Lỗi gọi local model:", e)
        return "エラー、ビッグブラザー..."
