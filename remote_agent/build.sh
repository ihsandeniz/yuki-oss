#!/bin/bash
# AliceAI Remote Agent — tek dosya executable build
# Çıktı: dist/alice-agent  (Linux/Mac) veya dist/alice-agent.exe (Windows)

set -e
cd "$(dirname "$0")"

echo "Bağımlılıklar kuruluyor..."
pip install -r requirements.txt

echo "PyInstaller ile derleniyor..."
pyinstaller --onefile --name alice-agent \
  --hidden-import mss \
  --hidden-import PIL \
  --hidden-import psutil \
  --hidden-import websockets \
  agent.py

echo ""
echo "✓ Derlendi: dist/alice-agent"
echo ""
echo "Kullanım:"
echo "  YUKI_SERVER=ws://192.168.1.x:8000/ws/agent YUKI_TOKEN=token ./dist/alice-agent"
