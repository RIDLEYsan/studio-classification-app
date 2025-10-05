"""
================================================
Streamlit スタジオ分類システム - 最適化版
再実行問題を解決し、処理の安定性を向上
================================================
ファイル名: streamlit_app_optimized.py
実行: streamlit run streamlit_app_optimized.py
================================================
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any
import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
from dotenv import load_dotenv
import hashlib
import time

# 環境変数読み込み
load_dotenv()

# ページ設定
st.set_page_config(page_title="スタジオ分類システム", page_icon="📸", layout="wide")

# ================================================
# カスタムCSS（変更なし）
# ================================================
st.markdown(
    """
<style>
    .tag-badge {
        background-color: #e3f2fd;
        color: #1976d2;
        padding: 6px 12px;
        border-radius: 16px;
        font-size: 14px;
        display: inline-block;
        margin: 2px;
    }
    .category-tag {
        background-color: #fff3e0;
        color: #f57c00;
        font-weight: bold;
    }
    .impression-tag {
        background-color: #f3e5f5;
        color: #7b1fa2;
    }
    .object-tag {
        background-color: #e8f5e9;
        color: #388e3c;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ================================================
# グローバル設定とシングルトン
# ================================================
@st.cache_resource
def init_database():
    """データベース接続を一度だけ初期化（キャッシュ）"""
    db_path = "studio_tags.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)

    # テーブル作成
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tag_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            classification_hierarchy TEXT,
            impression_tags TEXT,
            object_tags TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id TEXT UNIQUE,
            folder_name TEXT,
            broad_category TEXT,
            specific_item TEXT,
            impression_tags TEXT,
            object_tags TEXT,
            reason TEXT,
            purpose TEXT,
            features TEXT,
            image_count INTEGER,
            analyzed_at TIMESTAMP
        )
    """
    )

    conn.commit()
    return conn


@st.cache_resource
def init_gemini():
    """Gemini APIを一度だけ初期化（キャッシュ）"""
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        return None

    genai.configure(api_key=API_KEY)
    return genai.GenerativeModel("gemini-2.0-flash")


# ================================================
# セッションステート初期化（改善版）
# ================================================
def init_session_state():
    """セッションステートの初期化"""

    # 分析状態の管理
    if "analysis_in_progress" not in st.session_state:
        st.session_state.analysis_in_progress = False

    if "current_analysis_id" not in st.session_state:
        st.session_state.current_analysis_id = None

    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = []

    # タグ設定
    if "classification_hierarchy" not in st.session_state:
        st.session_state.classification_hierarchy = {
            "ハウススタジオ": ["和風", "洋風", "一軒家", "マンション", "アパート"],
            "オフィス": ["執務室", "会議室", "ロビー"],
            "飲食店": ["カフェ", "レストラン", "BAR", "居酒屋"],
            "その他": ["駐車場", "屋上", "オープンスペース"],
        }

    if "impression_tags" not in st.session_state:
        st.session_state.impression_tags = {
            "雰囲気": [
                {"label": "モダン", "slug": "modern"},
                {"label": "レトロ", "slug": "retro"},
                {"label": "ナチュラル", "slug": "natural"},
            ]
        }

    if "object_tags" not in st.session_state:
        st.session_state.object_tags = {
            "家具": [
                {"label": "ソファ", "slug": "sofa"},
                {"label": "テーブル", "slug": "table"},
            ]
        }


# ================================================
# 分析処理（非同期処理対応）
# ================================================
def generate_analysis_id(folder_name: str) -> str:
    """一意の分析IDを生成"""
    timestamp = datetime.now().isoformat()
    unique_string = f"{folder_name}_{timestamp}"
    return hashlib.md5(unique_string.encode()).hexdigest()[:12]


def perform_analysis(
    images: List[Image.Image], folder_name: str, options: Dict
) -> Dict:
    """画像分析を実行（エラーハンドリング強化）"""

    model = init_gemini()
    if not model:
        return {"error": "Gemini APIが初期化されていません"}

    # 分析IDを生成
    analysis_id = generate_analysis_id(folder_name)
    st.session_state.current_analysis_id = analysis_id

    try:
        # プロンプト構築
        prompt = f"""
あなたはプロの不動産・撮影スタジオコーディネーターです。
{len(images)}枚の写真を総合的に分析し、物件を分類してください。

分類階層:
{json.dumps(st.session_state.classification_hierarchy, ensure_ascii=False)}

印象タグ:
{json.dumps(st.session_state.impression_tags, ensure_ascii=False)}

オブジェクトタグ:
{json.dumps(st.session_state.object_tags, ensure_ascii=False)}

JSON形式で出力:
{{
    "大分類": "選択",
    "小項目": "選択",
    "印象タグ": ["slug1", "slug2"],
    "オブジェクトタグ": ["slug1", "slug2"],
    "判定理由": "50文字以内",
    "撮影用途": "用途例",
    "特徴": "特徴的な要素"
}}
"""

        # Gemini APIコール（タイムアウト対策）
        response = model.generate_content(
            [prompt] + images,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )

        result = json.loads(response.text)
        result["analysis_id"] = analysis_id
        result["フォルダ名"] = folder_name
        result["画像枚数"] = len(images)
        result["分析日時"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return result

    except Exception as e:
        return {
            "error": str(e),
            "analysis_id": analysis_id,
            "フォルダ名": folder_name,
            "画像枚数": len(images),
        }


def save_analysis_result(result: Dict, conn: sqlite3.Connection):
    """分析結果をデータベースに保存（重複チェック付き）"""

    # 重複チェック
    existing = conn.execute(
        "SELECT analysis_id FROM analysis_history WHERE analysis_id = ?",
        (result.get("analysis_id", ""),),
    ).fetchone()

    if not existing:
        conn.execute(
            """
            INSERT INTO analysis_history
            (analysis_id, folder_name, broad_category, specific_item,
             impression_tags, object_tags, reason, purpose, features,
             image_count, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                result.get("analysis_id", ""),
                result.get("フォルダ名", ""),
                result.get("大分類", ""),
                result.get("小項目", ""),
                json.dumps(result.get("印象タグ", []), ensure_ascii=False),
                json.dumps(result.get("オブジェクトタグ", []), ensure_ascii=False),
                result.get("判定理由", ""),
                result.get("撮影用途", ""),
                result.get("特徴", ""),
                result.get("画像枚数", 0),
                datetime.now(),
            ),
        )
        conn.commit()


# ================================================
# UIコンポーネント（改善版）
# ================================================
def render_analysis_tab():
    """画像分析タブ（改善版）"""

    st.subheader("📤 画像アップロードと分析")

    # 分析中の場合は警告を表示
    if st.session_state.analysis_in_progress:
        st.warning("⏳ 分析処理中です。しばらくお待ちください...")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_files = st.file_uploader(
            "画像を選択（複数可）",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="file_uploader",
        )

        if uploaded_files:
            st.success(f"📁 {len(uploaded_files)}枚の画像を選択中")

            # プレビュー（軽量化）
            with st.expander("画像プレビュー"):
                preview_cols = st.columns(4)
                for i, file in enumerate(uploaded_files[:4]):
                    preview_cols[i].image(file, use_container_width=True)

    with col2:
        folder_name = st.text_input(
            "物件名/フォルダ名",
            placeholder="例: 渋谷_スタジオA",
            key="folder_name_input",
        )

        # 分析ボタン（二重送信防止）
        analyze_button = st.button(
            "🚀 分析開始",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.analysis_in_progress,
            key="analyze_button",
        )

        if analyze_button and uploaded_files and folder_name:
            # 分析開始
            st.session_state.analysis_in_progress = True

            # プログレスバー表示
            progress_bar = st.progress(0, text="画像を準備中...")

            try:
                # 画像準備
                images = []
                for i, file in enumerate(uploaded_files):
                    progress_bar.progress(
                        (i + 1) / (len(uploaded_files) + 1),
                        text=f"画像を処理中... ({i + 1}/{len(uploaded_files)})",
                    )

                    image = Image.open(file)
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    # サイズ調整
                    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                    images.append(image)

                # 分析実行
                progress_bar.progress(0.9, text="AIが分析中...")

                result = perform_analysis(images, folder_name, {"use_all": True})

                if "error" not in result:
                    # 成功
                    st.session_state.analysis_results.append(result)

                    # データベースに保存
                    conn = init_database()
                    save_analysis_result(result, conn)

                    progress_bar.progress(1.0, text="完了！")
                    st.success("✅ 分析が完了しました！")
                    st.balloons()

                    # 結果を表示
                    with st.expander("📊 分析結果", expanded=True):
                        col_r1, col_r2 = st.columns(2)
                        with col_r1:
                            st.metric("大分類", result.get("大分類", "不明"))
                            st.metric("小項目", result.get("小項目", "不明"))
                        with col_r2:
                            st.metric("撮影用途", result.get("撮影用途", "不明"))
                            st.info(result.get("判定理由", ""))
                else:
                    st.error(f"エラー: {result['error']}")

            except Exception as e:
                st.error(f"処理中にエラーが発生しました: {e}")

            finally:
                # 分析完了
                st.session_state.analysis_in_progress = False
                time.sleep(1)
                st.rerun()


def render_history_tab():
    """履歴タブ（改善版）"""

    st.subheader("📊 分析履歴")

    conn = init_database()

    # ページネーション
    page_size = 10
    total_count = conn.execute("SELECT COUNT(*) FROM analysis_history").fetchone()[0]

    if total_count > 0:
        page = st.number_input(
            "ページ",
            min_value=1,
            max_value=(total_count + page_size - 1) // page_size,
            value=1,
        )

        offset = (page - 1) * page_size

        history = conn.execute(
            """
            SELECT * FROM analysis_history
            ORDER BY analyzed_at DESC
            LIMIT ? OFFSET ?
        """,
            (page_size, offset),
        ).fetchall()

        for record in history:
            with st.expander(f"📁 {record[2]} - {record[3]} ({record[9][:16]})"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**大分類**: {record[3]}")
                    st.write(f"**小項目**: {record[4]}")
                    st.write(f"**画像数**: {record[8]}枚")
                with col2:
                    st.write(f"**判定理由**: {record[6]}")
                    st.write(f"**撮影用途**: {record[7]}")
    else:
        st.info("まだ分析履歴がありません")


# ================================================
# メインアプリケーション
# ================================================
def main():
    """メインアプリケーション"""

    # 初期化
    init_session_state()

    # APIチェック
    model = init_gemini()
    if not model:
        st.error("❌ GEMINI_API_KEYが設定されていません")
        st.stop()

    # タイトル
    st.title("📸 スタジオ物件分類システム（最適化版）")

    # タブ構成
    tab1, tab2, tab3 = st.tabs(["📤 画像分析", "📊 分析履歴", "⚙️ 設定"])

    with tab1:
        render_analysis_tab()

    with tab2:
        render_history_tab()

    with tab3:
        st.info("設定管理機能は別途実装")


if __name__ == "__main__":
    main()
