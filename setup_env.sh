#!/bin/bash
echo "👉 Tạo virtualenv (.venv)..."
python3 -m venv .venv

echo "👉 Kích hoạt virtualenv..."
source .venv/bin/activate

echo "👉 Cài dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Xong! Để kích hoạt lại sau này: source .venv/bin/activate"
