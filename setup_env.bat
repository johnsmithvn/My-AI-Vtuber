@echo off
echo 👉 Tạo môi trường ảo .venv ...
python -m venv .venv

echo 👉 Kích hoạt môi trường ảo ...
call .venv\Scripts\activate

echo 👉 Cài thư viện từ requirements.txt ...
pip install --upgrade pip
pip install -r requirements.txt

echo ✅ Hoàn tất setup! Gõ: call .venv\Scripts\activate để kích hoạt lại sau này
pause
