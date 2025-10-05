import google.generativeai as genai
import os
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()
API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    print("❌ APIキーが設定されていません")
    exit()

genai.configure(api_key=API_KEY)

print("📋 利用可能なGeminiモデル一覧:\n")
print("-" * 60)

for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"✓ {m.name}")
        print(f"  サポート: {', '.join(m.supported_generation_methods)}")
        print()

print("-" * 60)
print("\n💡 上記のモデル名（models/を除いた部分）をコードで使用してください")
