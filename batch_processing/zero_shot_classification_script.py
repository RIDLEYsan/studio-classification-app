import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
from datetime import datetime
from pillow_heif import register_heif_opener

# HEICファイルのサポートを有効化
register_heif_opener()

# .envファイルから環境変数を読み込む
load_dotenv()

# APIキーの設定
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("APIキーが設定されていません。'.env'ファイルを確認してください。")
    exit()

print("Gemini APIキーを読み込みました。")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

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


def classify_property(folder_path, folder_name):
    """
    単一の物件フォルダ内の画像を分類する関数
    """
    # フォルダ内の画像ファイルを取得（.heicも追加）
    image_files = [
        f
        for f in os.listdir(folder_path)
        if f.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".heif")
        )
    ]

    if not image_files:
        print(f"  ⚠️ {folder_name}に画像がありません")
        return None

    print(f"  📸 {len(image_files)}枚の画像を分析中...")

    # すべての画像を読み込み（最大10枚に制限）
    images = []
    for image_file in image_files[:10]:  # メモリとAPI制限を考慮
        image_path = os.path.join(folder_path, image_file)
        try:
            image = PIL.Image.open(image_path)

            # HEICの場合、RGBに変換（透明度チャンネルを除去）
            if image.mode in ("RGBA", "LA", "P"):
                # 白背景でRGBに変換
                rgb_image = PIL.Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                rgb_image.paste(
                    image, mask=image.split()[-1] if image.mode == "RGBA" else None
                )
                image = rgb_image
            elif image.mode != "RGB":
                image = image.convert("RGB")

            # 画像サイズを適度に縮小（必要に応じて）
            max_size = (1024, 1024)
            image.thumbnail(max_size, PIL.Image.Resampling.LANCZOS)
            images.append(image)

        except Exception as e:
            print(f"    ⚠️ 画像読み込みエラー ({image_file}): {e}")
            # HEICファイルの場合、特別なエラーメッセージ
            if image_file.lower().endswith((".heic", ".heif")):
                print(
                    f"    💡 HEICファイルの読み込みに失敗しました。pillow-heifがインストールされているか確認してください。"
                )

    if not images:
        return None

    # プロンプト
    broad_categories = ", ".join(CLASSIFICATION_MAP.keys())
    specific_categories = ", ".join(sum(CLASSIFICATION_MAP.values(), []))

    prompt = f"""
あなたは不動産・撮影スタジオの専門家です。
以下の{len(images)}枚の写真は、同一物件の様々な場所を撮影したものです。
これらの写真を総合的に分析し、この物件全体がどのような施設なのかを判定してください。

【重要な判定基準】
- 建物全体の用途と特徴
- 内装のスタイルと統一感
- 設備や家具から推測される使用目的
- 撮影スタジオとしての活用可能性

大分類の選択肢: {broad_categories}
小項目の選択肢: {specific_categories}

JSON形式で以下のように簡潔に出力してください：
{{
    "大分類": "最も適切な大分類を1つ",
    "小項目": "最も適切な小項目を1つ",
    "判定理由": "なぜそう判断したか30文字以内で簡潔に"
}}
"""

    try:
        # Geminiに送信
        content_parts = [prompt] + images
        response = model.generate_content(
            content_parts, generation_config={"response_mime_type": "application/json"}
        )

        # 結果をパース
        result = json.loads(response.text)
        result["フォルダ名"] = folder_name
        result["画像枚数"] = len(image_files)

        return result

    except Exception as e:
        print(f"    ❌ 分析エラー: {e}")
        return {
            "フォルダ名": folder_name,
            "大分類": "エラー",
            "小項目": "エラー",
            "判定理由": str(e)[:30],
            "画像枚数": len(image_files),
        }


def main():
    """
    メイン処理：studio_photos内の各フォルダを処理
    """
    base_folder = "studio_photos"

    if not os.path.exists(base_folder):
        print(f"❌ {base_folder}フォルダが見つかりません")
        exit()

    # サブフォルダのリストを取得
    subfolders = [
        f
        for f in os.listdir(base_folder)
        if os.path.isdir(os.path.join(base_folder, f))
    ]

    if not subfolders:
        print(f"❌ {base_folder}内にサブフォルダがありません")
        print("物件ごとにフォルダを作成して画像を配置してください")
        exit()

    print(f"\n📂 {len(subfolders)}個の物件フォルダを発見")
    print("=" * 60)

    # 結果を保存するリスト
    all_results = []

    # 各フォルダを処理
    for i, folder_name in enumerate(sorted(subfolders), 1):
        print(f"\n[{i}/{len(subfolders)}] 処理中: {folder_name}")
        print("-" * 40)

        folder_path = os.path.join(base_folder, folder_name)
        result = classify_property(folder_path, folder_name)

        if result:
            all_results.append(result)
            print(f"  ✅ 大分類: {result['大分類']}")
            print(f"  📝 小項目: {result['小項目']}")
            print(f"  💡 理由: {result['判定理由']}")

    # 結果をCSV形式でも保存（Excelで開きやすい）
    if all_results:
        # JSON保存
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = f"classification_results_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        # CSV保存
        csv_file = f"classification_results_{timestamp}.csv"
        with open(csv_file, "w", encoding="utf-8-sig") as f:  # BOM付きUTF-8
            f.write("フォルダ名,大分類,小項目,判定理由,画像枚数\n")
            for r in all_results:
                f.write(
                    f"{r['フォルダ名']},{r['大分類']},{r['小項目']},{r['判定理由']},{r.get('画像枚数', 0)}\n"
                )

        # 結果サマリーの表示
        print("\n" + "=" * 60)
        print("📊 分類結果サマリー")
        print("=" * 60)
        print(f"{'フォルダ名':<20} {'大分類':<10} {'小項目':<15} {'判定理由':<30}")
        print("-" * 80)
        for r in all_results:
            print(
                f"{r['フォルダ名']:<20} {r['大分類']:<10} {r['小項目']:<15} {r['判定理由']:<30}"
            )

        print("\n" + "=" * 60)
        print(f"✅ 処理完了: {len(all_results)}件の物件を分類しました")
        print(f"📄 結果ファイル:")
        print(f"   - JSON: {json_file}")
        print(f"   - CSV:  {csv_file}")

        # カテゴリ別集計
        category_count = {}
        for r in all_results:
            cat = r["大分類"]
            category_count[cat] = category_count.get(cat, 0) + 1

        print(f"\n📈 カテゴリ別集計:")
        for cat, count in sorted(category_count.items()):
            print(f"   - {cat}: {count}件")
    else:
        print("\n❌ 処理可能な物件がありませんでした")


if __name__ == "__main__":
    print("🏠 物件分類システム起動")
    print("=" * 60)
    main()
