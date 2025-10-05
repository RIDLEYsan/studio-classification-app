import os
import json
import base64
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import PIL.Image
import io

# .envファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__)
CORS(app)

# 分類項目リスト
CLASSIFICATION_MAP = {
    "ハウススタジオ": ["和風", "洋風", "一軒家", "マンション", "アパート"],
    "公園": ["公園"],
    "オフィス": ["執務室", "会議室", "ロビー"],
    "商業施設": [
        "ショッピングモール",
        "遊園地",
        "水族館/動物園/植物園",
        "博物館/美術館",
        "映画館",
        "ボーリング/ゲームセンター/ビリヤード",
        "商店街",
    ],
    "学校": ["小学校", "中学校", "高校", "大学/専門学校", "幼稚園/保育園"],
    "病院": ["受付", "手術室"],
    "店舗": ["コンビニ", "ドラッグストア", "スーパー", "アパレル", "ガソリンスタンド"],
    "飲食店": ["中華料理屋", "レストラン", "カフェ", "居酒屋", "食堂", "BAR"],
    "自然": ["山", "川", "海", "草原", "森", "湖/池", "花畑", "道"],
    "その他": [
        "駐車場",
        "屋上",
        "神社仏閣",
        "オープンスペース",
        "夜景/イルミネーション",
    ],
}


# Few-shot用のサンプル画像を読み込む関数
def load_example_images():
    """few_shot_examplesフォルダから例示用画像を読み込む"""
    examples = {}
    example_dir = "few_shot_examples"

    # 各カテゴリのサンプル画像を読み込み
    example_files = {
        "house_studio": ["house_studio_japanese.jpg", "house_studio_western.jpg"],
        "commercial": ["commercial_mall.jpg", "commercial_museum.jpg"],
        "restaurant": ["restaurant_cafe.jpg", "restaurant_japanese.jpg"],
        "office": ["office_meeting.jpg", "office_lobby.jpg"],
        "nature": ["nature_mountain.jpg", "nature_sea.jpg"],
    }

    for category, files in example_files.items():
        examples[category] = []
        for file in files:
            filepath = os.path.join(example_dir, file)
            if os.path.exists(filepath):
                image = PIL.Image.open(filepath)
                examples[category].append(image)
                print(f"✓ 読み込み成功: {file}")
            else:
                print(f"✗ ファイルが見つかりません: {filepath}")

    return examples


# モデルとサンプル画像の初期化
model = None
EXAMPLE_IMAGES = None


@app.route("/classify_with_fewshot", methods=["POST"])
def classify_with_fewshot():
    """
    Few-shot学習を使った統合分類エンドポイント
    """
    try:
        data = request.json
        images_base64 = data.get("images", [])

        if not images_base64:
            return jsonify({"error": "No images provided"}), 400

        # Base64画像をPIL Imageに変換
        user_images = []
        for img_base64 in images_base64:
            if "," in img_base64:
                img_base64 = img_base64.split(",")[1]
            img_bytes = base64.b64decode(img_base64)
            img = PIL.Image.open(io.BytesIO(img_bytes))
            user_images.append(img)

        # Few-shot プロンプトを構築
        content_parts = []

        # プロンプトの説明
        content_parts.append(
            """
あなたは映画・TV制作のロケーションコーディネーターです。
以下に示す例を参考に、提供された画像の場所を分類してください。

【例示学習セクション】
以下の例を学習してください：
        """
        )

        # Few-shot例を追加（利用可能な例のみ）
        if EXAMPLE_IMAGES:
            # ハウススタジオの例
            if "house_studio" in EXAMPLE_IMAGES and EXAMPLE_IMAGES["house_studio"]:
                for img in EXAMPLE_IMAGES["house_studio"][:1]:  # 1例のみ使用
                    content_parts.append(img)
                    content_parts.append(
                        "→ 分類: ハウススタジオ（和風または洋風の撮影用住宅）"
                    )

            # 商業施設の例
            if "commercial" in EXAMPLE_IMAGES and EXAMPLE_IMAGES["commercial"]:
                for img in EXAMPLE_IMAGES["commercial"][:1]:
                    content_parts.append(img)
                    content_parts.append(
                        "→ 分類: 商業施設（ショッピングモールや博物館など）"
                    )

            # 飲食店の例
            if "restaurant" in EXAMPLE_IMAGES and EXAMPLE_IMAGES["restaurant"]:
                for img in EXAMPLE_IMAGES["restaurant"][:1]:
                    content_parts.append(img)
                    content_parts.append("→ 分類: 飲食店（カフェやレストランなど）")

        # ユーザーの画像を追加
        content_parts.append(
            f"""

【判定対象】
以下の{len(user_images)}枚の画像を分析し、上記の例を参考に分類してください。

分類カテゴリー：
大分類: {", ".join(CLASSIFICATION_MAP.keys())}
各カテゴリーの小項目: {json.dumps(CLASSIFICATION_MAP, ensure_ascii=False, indent=2)}

JSON形式で回答してください：
{{
    "大分類": "最も適切な大分類",
    "小項目": "最も適切な小項目",
    "確信度": "1-10のスコア",
    "判定理由": "Few-shot例との類似点を含めた判断根拠",
    "類似した例": "参考にしたFew-shot例があれば記載"
}}
        """
        )

        # ユーザーの画像を追加
        for img in user_images:
            content_parts.append(img)

        # Geminiで判定
        if model is None:
            return jsonify({"error": "Model not initialized"}), 500

        response = model.generate_content(
            content_parts, generation_config={"response_mime_type": "application/json"}
        )

        result = json.loads(response.text)

        print("\n--- Few-shot判定結果 ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        return jsonify(result), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/test_examples", methods=["GET"])
def test_examples():
    """サンプル画像の読み込み状態を確認するエンドポイント"""
    if EXAMPLE_IMAGES:
        status = {}
        for category, images in EXAMPLE_IMAGES.items():
            status[category] = f"{len(images)}枚の画像"
        return jsonify({"status": "OK", "examples": status}), 200
    else:
        return jsonify({"status": "No examples loaded"}), 200


if __name__ == "__main__":
    # APIキーの確認
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        print("エラー: GEMINI_API_KEYが設定されていません")
        exit(1)

    print("✅ Gemini APIキーを読み込みました")
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")  # 最新モデルを使用

    # Few-shot用のサンプル画像を読み込み
    print("\n📸 Few-shot用サンプル画像を読み込み中...")
    EXAMPLE_IMAGES = load_example_images()

    if not EXAMPLE_IMAGES or all(len(v) == 0 for v in EXAMPLE_IMAGES.values()):
        print("⚠️  警告: Few-shot用のサンプル画像が見つかりません")
        print("few_shot_examplesフォルダに画像を配置してください")
    else:
        total_images = sum(len(v) for v in EXAMPLE_IMAGES.values())
        print(f"✅ {total_images}枚のサンプル画像を読み込みました")

    print("\nFlaskサーバーを起動します...")
    app.run(debug=True, port=5000)
