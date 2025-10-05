cd /Users/Hironori/Python.py/studio_classification_project

cat > streamlit_app/streamlit_classifier_sqlite_fixed.py << 'ENDOFFILE'
"""
================================================
Streamlit スタジオ分類システム - 改善版UI
================================================
ファイル名: streamlit_classifier_sqlite.py
実行: streamlit run streamlit_classifier_sqlite.py
================================================
"""

import os
import json
import sqlite3
import re
import traceback
from datetime import datetime
from typing import List, Dict, Any
import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

# ページ設定
st.set_page_config(page_title="スタジオ分類システム", page_icon="📸", layout="wide")

# カスタムCSS
st.markdown(
    """
<style>
    /* タグ表示用のスタイル */
    .tag-container {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 10px 0;
    }

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

    .tag-group {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        background-color: #fafafa;
    }

    .tag-group-title {
        font-weight: bold;
        color: #424242;
        margin-bottom: 8px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ================================================
# ユーティリティ関数
# ================================================


def safe_json_parse(response_text, fallback_data=None):
    """
    Safely parse JSON from API response with fallback handling
    """
    try:
        # First, try direct parsing
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        json_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON-like content without code blocks
        json_match = re.search(r"(\{.*?\})", response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Return fallback data or error structure
        if fallback_data is not None:
            return fallback_data
        return {"error": "JSON parsing failed", "raw_response": response_text}


def parse_impression_response(response_text):
    """印象タグ用のフォールバック処理"""
    return safe_json_parse(
        response_text,
        {
            "雰囲気": [{"label": "分析失敗", "slug": "analysis_failed"}],
            "色調": [{"label": "不明", "slug": "unknown"}],
            "空間特性": [{"label": "不明", "slug": "unknown"}],
        },
    )


def parse_object_response(response_text):
    """オブジェクトタグ用のフォールバック処理"""
    return safe_json_parse(
        response_text,
        {
            "家具": [{"label": "分析失敗", "slug": "analysis_failed"}],
            "設備": [{"label": "不明", "slug": "unknown"}],
            "装飾・小物": [{"label": "不明", "slug": "unknown"}],
            "建築要素": [{"label": "不明", "slug": "unknown"}],
        },
    )


def parse_classification_response(response_text):
    """分類結果用のフォールバック処理"""
    return safe_json_parse(
        response_text,
        {
            "大分類": "不明",
            "小項目": "不明",
            "印象タグ": [],
            "オブジェクトタグ": [],
            "判定理由": "分析に失敗しました",
            "撮影用途": "汎用",
            "特徴": "不明",
        },
    )


# ================================================
# データ構造定義（階層型）
# ================================================
DEFAULT_CLASSIFICATION_HIERARCHY = {
    "ハウススタジオ": ["和風", "洋風", "一軒家", "マンション", "アパート"],
    "公園": ["都市公園", "自然公園", "遊具あり", "芝生広場"],
    "オフィス": ["執務室", "会議室", "ロビー", "受付"],
    "商業施設": [
        "ショッピングモール",
        "遊園地",
        "水族館/動物園",
        "博物館/美術館",
        "映画館",
        "商店街",
    ],
    "学校": ["小学校", "中学校", "高校", "大学/専門学校", "幼稚園/保育園"],
    "病院": ["受付", "待合室", "診察室", "病室", "手術室"],
    "店舗": ["コンビニ", "ドラッグストア", "スーパー", "アパレル", "ガソリンスタンド"],
    "飲食店": [
        "中華料理屋",
        "レストラン",
        "カフェ",
        "居酒屋",
        "食堂",
        "BAR",
        "ファーストフード",
    ],
    "自然": ["山", "川", "海", "草原", "森", "湖/池", "花畑"],
    "その他": [
        "駐車場",
        "屋上",
        "神社仏閣",
        "オープンスペース",
        "夜景/イルミネーション",
    ],
}

DEFAULT_IMPRESSION_TAGS = {
    "雰囲気": [
        {"label": "モダン", "slug": "modern"},
        {"label": "レトロ", "slug": "retro"},
        {"label": "ナチュラル", "slug": "natural"},
        {"label": "高級感", "slug": "luxury"},
        {"label": "カジュアル", "slug": "casual"},
        {"label": "和風", "slug": "japanese_style"},
        {"label": "洋風", "slug": "western_style"},
        {"label": "インダストリアル", "slug": "industrial"},
        {"label": "ミニマリスト", "slug": "minimalist"},
        {"label": "アーティスティック", "slug": "artistic"},
    ],
    "色調": [
        {"label": "明るい", "slug": "bright"},
        {"label": "暗い", "slug": "dark"},
        {"label": "暖色系", "slug": "warm_colors"},
        {"label": "寒色系", "slug": "cool_colors"},
        {"label": "モノトーン", "slug": "monotone"},
        {"label": "カラフル", "slug": "colorful"},
        {"label": "パステル", "slug": "pastel"},
        {"label": "ビビッド", "slug": "vivid"},
    ],
    "空間特性": [
        {"label": "広々", "slug": "spacious"},
        {"label": "コンパクト", "slug": "compact"},
        {"label": "開放的", "slug": "open"},
        {"label": "プライベート", "slug": "private"},
        {"label": "天井が高い", "slug": "high_ceiling"},
        {"label": "窓が多い", "slug": "many_windows"},
    ],
}

DEFAULT_OBJECT_TAGS = {
    "家具": [
        {"label": "ソファ", "slug": "sofa"},
        {"label": "テーブル", "slug": "table"},
        {"label": "椅子", "slug": "chair"},
        {"label": "ベッド", "slug": "bed"},
        {"label": "棚", "slug": "shelf"},
        {"label": "デスク", "slug": "desk"},
        {"label": "収納", "slug": "storage"},
    ],
    "設備": [
        {"label": "キッチン", "slug": "kitchen"},
        {"label": "バスルーム", "slug": "bathroom"},
        {"label": "トイレ", "slug": "toilet"},
        {"label": "エアコン", "slug": "ac"},
        {"label": "照明器具", "slug": "lighting"},
        {"label": "暖炉", "slug": "fireplace"},
        {"label": "エレベーター", "slug": "elevator"},
    ],
    "装飾・小物": [
        {"label": "カーテン", "slug": "curtain"},
        {"label": "絵画", "slug": "painting"},
        {"label": "観葉植物", "slug": "plants"},
        {"label": "ラグ", "slug": "rug"},
        {"label": "時計", "slug": "clock"},
        {"label": "鏡", "slug": "mirror"},
    ],
    "建築要素": [
        {"label": "窓", "slug": "window"},
        {"label": "ドア", "slug": "door"},
        {"label": "階段", "slug": "stairs"},
        {"label": "柱", "slug": "pillar"},
        {"label": "梁", "slug": "beam"},
        {"label": "バルコニー", "slug": "balcony"},
    ],
}


# ================================================
# SQLiteデータベース管理
# ================================================
class TagDatabase:
    def __init__(self, db_path="studio_tags.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
                    folder_name TEXT,
                    broad_category TEXT,
                    specific_item TEXT,
                    impression_tags TEXT,
                    object_tags TEXT,
                    reason TEXT,
                    purpose TEXT,
                    image_count INTEGER,
                    analyzed_at TIMESTAMP
                )
            """
            )


# データベース初期化
db = TagDatabase()

# ================================================
# Gemini API設定
# ================================================
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    st.error("❌ GEMINI_API_KEYが設定されていません")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# ================================================
# セッションステート初期化
# ================================================
if "classification_hierarchy" not in st.session_state:
    st.session_state.classification_hierarchy = DEFAULT_CLASSIFICATION_HIERARCHY.copy()

if "impression_tags" not in st.session_state:
    st.session_state.impression_tags = DEFAULT_IMPRESSION_TAGS.copy()

if "object_tags" not in st.session_state:
    st.session_state.object_tags = DEFAULT_OBJECT_TAGS.copy()


# ================================================
# ユーティリティ関数
# ================================================
def render_tags_visual(tags: Dict, tag_type: str = "default"):
    """タグを視覚的に表示"""
    html_content = '<div class="tag-container">'

    if tag_type == "hierarchy":
        for category, items in tags.items():
            html_content += f'<div class="tag-group">'
            html_content += f'<div class="tag-group-title">{category}</div>'
            for item in items:
                html_content += f'<span class="tag-badge category-tag">{item}</span>'
            html_content += "</div>"

    elif tag_type == "impression" or tag_type == "object":
        css_class = f"{tag_type}-tag"
        for category, items in tags.items():
            html_content += f'<div class="tag-group">'
            html_content += f'<div class="tag-group-title">{category}</div>'
            for item in items:
                html_content += (
                    f'<span class="tag-badge {css_class}">{item["label"]}</span>'
                )
            html_content += "</div>"

    html_content += "</div>"
    return html_content


# ================================================
# メインUI
# ================================================
st.title("📸 スタジオ物件分類システム")
st.markdown("### 階層型タグ管理・視覚的表示対応版")

# タブ構成
tab1, tab2, tab3, tab4 = st.tabs(
    ["🏷️ タグ管理", "📤 画像分析", "📊 分析結果", "📈 統計"]
)

# タグ管理タブ
with tab1:
    st.subheader("🎨 タグ管理")

    # タブで分類階層、印象タグ、オブジェクトタグを管理
    tag_tab1, tag_tab2, tag_tab3 = st.tabs(["分類階層", "印象タグ", "オブジェクトタグ"])

    with tag_tab1:
        st.markdown("### 🗂️ 分類階層")

        # 視覚的表示のみ
        st.markdown("### 現在の分類体系")
        st.markdown(
            render_tags_visual(st.session_state.classification_hierarchy, "hierarchy"),
            unsafe_allow_html=True,
        )

    with tag_tab2:
        # 編集モードの選択
        edit_mode_impression = st.radio(
            "編集方法",
            ["表示のみ", "個別編集", "AI整形", "JSON編集"],
            key="edit_mode_impression",
            horizontal=True,
        )

        if edit_mode_impression == "個別編集":
            st.markdown("### 📝 印象タグの個別編集")

            # 既存のカテゴリを編集
            for category in list(st.session_state.impression_tags.keys()):
                with st.expander(f"🎨 {category}", expanded=False):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        # 既存タグの表示と編集
                        st.markdown("**既存のタグ:**")
                        for i, item in enumerate(
                            st.session_state.impression_tags[category]
                        ):
                            col_label, col_slug, col_del = st.columns([2, 2, 1])

                            # ラベルとスラッグの編集
                            new_label = col_label.text_input(
                                f"ラベル {i+1}",
                                value=item["label"],
                                key=f"impression_label_{category}_{i}",
                            )
                            new_slug = col_slug.text_input(
                                f"スラッグ {i+1}",
                                value=item["slug"],
                                key=f"impression_slug_{category}_{i}",
                            )

                            # 変更を反映
                            if new_label != item["label"] or new_slug != item["slug"]:
                                st.session_state.impression_tags[category][i] = {
                                    "label": new_label,
                                    "slug": new_slug,
                                }

                            # 削除ボタン
                            if col_del.button(
                                "🗑️", key=f"del_impression_item_{category}_{i}"
                            ):
                                st.session_state.impression_tags[category].pop(i)
                                st.rerun()

                        # 新しいタグを追加
                        st.divider()
                        st.markdown("**新しいタグを追加:**")
                        col_new_label, col_new_slug, col_add = st.columns([2, 2, 1])

                        new_item_label = col_new_label.text_input(
                            "新しいラベル", key=f"new_impression_label_{category}"
                        )
                        new_item_slug = col_new_slug.text_input(
                            "新しいスラッグ", key=f"new_impression_slug_{category}"
                        )

                        if col_add.button(
                            "➕ 追加", key=f"add_impression_item_{category}"
                        ):
                            if new_item_label and new_item_slug:
                                st.session_state.impression_tags[category].append(
                                    {"label": new_item_label, "slug": new_item_slug}
                                )
                                st.success(f"✅ 「{new_item_label}」を追加しました")
                                st.rerun()

                    with col2:
                        if st.button(
                            f"🗑️ カテゴリ削除", key=f"del_impression_category_{category}"
                        ):
                            del st.session_state.impression_tags[category]
                            st.rerun()

            # 新しいカテゴリを追加
            st.divider()
            with st.form("add_impression_category"):
                st.markdown("### ➕ 新規カテゴリ追加")
                new_category = st.text_input("カテゴリ名")
                new_label = st.text_input("最初のタグのラベル")
                new_slug = st.text_input("最初のタグのスラッグ")

                if st.form_submit_button("追加", type="primary"):
                    if new_category and new_label and new_slug:
                        st.session_state.impression_tags[new_category] = [
                            {"label": new_label, "slug": new_slug}
                        ]
                        st.success(f"✅ カテゴリ「{new_category}」を追加しました")
                        st.rerun()

        elif edit_mode_impression == "AI整形":
            st.markdown("### 🤖 AIでタグを整形")
            st.info(
                "自由にテキストを入力してください。AIが適切なカテゴリに分類します。"
            )

            raw_impression_text = st.text_area(
                "印象タグを入力（カンマ区切りまたは改行）",
                placeholder="例:\nモダン\nレトロ\n明るい雰囲気\n開放的な空間\nナチュラル\n高級感がある",
                height=150,
                key="raw_impression",
            )

            if st.button("🤖 AIで整形", key="format_impression", type="primary"):
                if raw_impression_text:
                    with st.spinner("AIが整形中..."):
                        prompt = f"""
以下のテキストを、撮影スタジオの印象を表すタグとして整理してください。
適切なカテゴリ（雰囲気、色調、空間特性など）に分類し、各タグに日本語ラベルと英語スラッグを付けてください。

入力テキスト:
{raw_impression_text}

以下のJSON形式で出力してください：
{{
    "雰囲気": [{{"label": "モダン", "slug": "modern"}}, ...],
    "色調": [{{"label": "明るい", "slug": "bright"}}, ...],
    "空間特性": [{{"label": "広々", "slug": "spacious"}}, ...],
    "その他適切なカテゴリ": [...]
}}

スラッグは英語小文字とアンダースコアのみ使用してください。
"""
                        try:
                            response = model.generate_content(
                                prompt,
                                generation_config=genai.GenerationConfig(
                                    temperature=0.3,
                                ),
                            )

                            # 安全なJSON解析を使用
                            formatted_tags = parse_impression_response(response.text)

                            if "error" in formatted_tags:
                                st.error(
                                    f"AI応答の解析に失敗しました: {formatted_tags['error']}"
                                )
                                with st.expander("AIの生の応答を確認"):
                                    st.text_area(
                                        "応答内容",
                                        formatted_tags.get("raw_response", ""),
                                        height=200,
                                    )
                            else:
                                st.session_state.impression_tags = formatted_tags
                                st.success("✅ AIによる整形が完了しました！")
                                st.json(formatted_tags)
                                st.rerun()
                        except Exception as e:
                            st.error(f"整形エラー: {e}")

        elif edit_mode_impression == "JSON編集":
            st.markdown("### 📝 JSON直接編集")
            edited_impression = st.text_area(
                "JSON形式で編集",
                json.dumps(
                    st.session_state.impression_tags, ensure_ascii=False, indent=2
                ),
                height=300,
            )
            if st.button("💾 保存", key="save_impression"):
                try:
                    st.session_state.impression_tags = json.loads(edited_impression)
                    st.success("✅ 保存しました")
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"JSONエラー: {e}")

        else:  # 表示のみ
            st.markdown("### 現在の印象タグ")
            st.markdown(
                render_tags_visual(st.session_state.impression_tags, "impression"),
                unsafe_allow_html=True,
            )

    with tag_tab3:
        # 編集モードの選択
        edit_mode_object = st.radio(
            "編集方法",
            ["表示のみ", "個別編集", "AI整形", "JSON編集"],
            key="edit_mode_object",
            horizontal=True,
        )

        if edit_mode_object == "個別編集":
            st.markdown("### 📝 オブジェクトタグの個別編集")

            # 既存のカテゴリを編集
            for category in list(st.session_state.object_tags.keys()):
                with st.expander(f"🔧 {category}", expanded=False):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        # 既存タグの表示と編集
                        st.markdown("**既存のタグ:**")
                        for i, item in enumerate(
                            st.session_state.object_tags[category]
                        ):
                            col_label, col_slug, col_del = st.columns([2, 2, 1])

                            # ラベルとスラッグの編集
                            new_label = col_label.text_input(
                                f"ラベル {i+1}",
                                value=item["label"],
                                key=f"object_label_{category}_{i}",
                            )
                            new_slug = col_slug.text_input(
                                f"スラッグ {i+1}",
                                value=item["slug"],
                                key=f"object_slug_{category}_{i}",
                            )

                            # 変更を反映
                            if new_label != item["label"] or new_slug != item["slug"]:
                                st.session_state.object_tags[category][i] = {
                                    "label": new_label,
                                    "slug": new_slug,
                                }

                            # 削除ボタン
                            if col_del.button(
                                "🗑️", key=f"del_object_item_{category}_{i}"
                            ):
                                st.session_state.object_tags[category].pop(i)
                                st.rerun()

                        # 新しいタグを追加
                        st.divider()
                        st.markdown("**新しいタグを追加:**")
                        col_new_label, col_new_slug, col_add = st.columns([2, 2, 1])

                        new_item_label = col_new_label.text_input(
                            "新しいラベル", key=f"new_object_label_{category}"
                        )
                        new_item_slug = col_new_slug.text_input(
                            "新しいスラッグ", key=f"new_object_slug_{category}"
                        )

                        if col_add.button("➕ 追加", key=f"add_object_item_{category}"):
                            if new_item_label and new_item_slug:
                                st.session_state.object_tags[category].append(
                                    {"label": new_item_label, "slug": new_item_slug}
                                )
                                st.success(f"✅ 「{new_item_label}」を追加しました")
                                st.rerun()

                    with col2:
                        if st.button(
                            f"🗑️ カテゴリ削除", key=f"del_object_category_{category}"
                        ):
                            del st.session_state.object_tags[category]
                            st.rerun()

            # 新しいカテゴリを追加
            st.divider()
            with st.form("add_object_category"):
                st.markdown("### ➕ 新規カテゴリ追加")
                new_category = st.text_input("カテゴリ名")
                new_label = st.text_input("最初のタグのラベル")
                new_slug = st.text_input("最初のタグのスラッグ")

                if st.form_submit_button("追加", type="primary"):
                    if new_category and new_label and new_slug:
                        st.session_state.object_tags[new_category] = [
                            {"label": new_label, "slug": new_slug}
                        ]
                        st.success(f"✅ カテゴリ「{new_category}」を追加しました")
                        st.rerun()

        elif edit_mode_object == "AI整形":
            st.markdown("### 🤖 AIでタグを整形")
            st.info(
                "物体や設備を自由に入力してください。AIが適切なカテゴリに分類します。"
            )

            raw_object_text = st.text_area(
                "オブジェクトタグを入力（カンマ区切りまたは改行）",
                placeholder="例:\nソファ\n大きなテーブル\n観葉植物\nキッチン設備\n窓が多い\n階段\n暖炉",
                height=150,
                key="raw_object",
            )

            if st.button("🤖 AIで整形", key="format_object", type="primary"):
                if raw_object_text:
                    with st.spinner("AIが整形中..."):
                        prompt = f"""
以下のテキストを、撮影スタジオ内のオブジェクトを表すタグとして整理してください。
適切なカテゴリ（家具、設備、装飾・小物、建築要素など）に分類し、各タグに日本語ラベルと英語スラッグを付けてください。

入力テキスト:
{raw_object_text}

以下のJSON形式で出力してください：
{{
    "家具": [{{"label": "ソファ", "slug": "sofa"}}, ...],
    "設備": [{{"label": "キッチン", "slug": "kitchen"}}, ...],
    "装飾・小物": [{{"label": "観葉植物", "slug": "plants"}}, ...],
    "建築要素": [{{"label": "窓", "slug": "window"}}, ...],
    "その他適切なカテゴリ": [...]
}}

スラッグは英語小文字とアンダースコアのみ使用してください。
"""
                        try:
                            response = model.generate_content(
                                prompt,
                                generation_config=genai.GenerationConfig(
                                    temperature=0.3,
                                ),
                            )

                            # 安全なJSON解析を使用
                            formatted_tags = parse_object_response(response.text)

                            if "error" in formatted_tags:
                                st.error(
                                    f"AI応答の解析に失敗しました: {formatted_tags['error']}"
                                )
                                with st.expander("AIの生の応答を確認"):
                                    st.text_area(
                                        "応答内容",
                                        formatted_tags.get("raw_response", ""),
                                        height=200,
                                    )
                            else:
                                st.session_state.object_tags = formatted_tags
                                st.success("✅ AIによる整形が完了しました！")
                                st.json(formatted_tags)
                                st.rerun()
                        except Exception as e:
                            st.error(f"整形エラー: {e}")

        elif edit_mode_object == "JSON編集":
            st.markdown("### 📝 JSON直接編集")
            edited_object = st.text_area(
                "JSON形式で編集",
                json.dumps(st.session_state.object_tags, ensure_ascii=False, indent=2),
                height=300,
            )
            if st.button("💾 保存", key="save_object"):
                try:
                    st.session_state.object_tags = json.loads(edited_object)
                    st.success("✅ 保存しました")
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"JSONエラー: {e}")

        else:  # 表示のみ
            st.markdown("### 現在のオブジェクトタグ")
            st.markdown(
                render_tags_visual(st.session_state.object_tags, "object"),
                unsafe_allow_html=True,
            )

    # 設定の保存/読み込み
    st.divider()
    st.subheader("💾 設定管理")

    col1, col2 = st.columns(2)
    with col1:
        config_name = st.text_input("設定名")
        if st.button("現在の設定を保存", type="primary"):
            if config_name:
                # SQLiteに保存
                with sqlite3.connect(db.db_path) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO tag_configs
                        (name, classification_hierarchy, impression_tags, object_tags, created_at, updated_at)
                        VALUES (?, ?, ?, ?,
                            COALESCE((SELECT created_at FROM tag_configs WHERE name = ?), ?),
                            ?)
                    """,
                        (
                            config_name,
                            json.dumps(
                                st.session_state.classification_hierarchy,
                                ensure_ascii=False,
                            ),
                            json.dumps(
                                st.session_state.impression_tags, ensure_ascii=False
                            ),
                            json.dumps(
                                st.session_state.object_tags, ensure_ascii=False
                            ),
                            config_name,
                            datetime.now(),
                            datetime.now(),
                        ),
                    )
                st.success(f"✅ 「{config_name}」を保存しました")

    with col2:
        # 保存済み設定の読み込み
        with sqlite3.connect(db.db_path) as conn:
            configs = conn.execute(
                "SELECT name, updated_at FROM tag_configs ORDER BY updated_at DESC"
            ).fetchall()

        if configs:
            selected = st.selectbox("保存済み設定", [c[0] for c in configs])
            if st.button("設定を読み込む"):
                with sqlite3.connect(db.db_path) as conn:
                    result = conn.execute(
                        "SELECT classification_hierarchy, impression_tags, object_tags FROM tag_configs WHERE name = ?",
                        (selected,),
                    ).fetchone()

                    if result:
                        st.session_state.classification_hierarchy = json.loads(
                            result[0]
                        )
                        st.session_state.impression_tags = json.loads(result[1])
                        st.session_state.object_tags = json.loads(result[2])
                        st.success(f"✅ 「{selected}」を読み込みました")
                        st.rerun()

# 画像分析タブ
with tab2:
    st.subheader("📤 画像アップロードと分析")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_files = st.file_uploader(
            "画像を選択（複数可）",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            st.success(f"📁 {len(uploaded_files)}枚の画像を選択中")

            # プレビュー
            with st.expander("画像プレビュー", expanded=True):
                preview_cols = st.columns(4)
                for i, file in enumerate(uploaded_files[:8]):
                    preview_cols[i % 4].image(
                        file, caption=file.name, use_container_width=True
                    )

    with col2:
        st.markdown("### 分析設定")

        folder_name = st.text_input(
            "物件名/フォルダ名", placeholder="例: 渋谷_スタジオA"
        )

        st.markdown("### 使用するタグ")
        use_classification = st.checkbox("分類階層", value=True)
        use_impression = st.checkbox("印象タグ", value=True)
        use_object = st.checkbox("オブジェクトタグ", value=True)

        if st.button("🚀 分析開始", type="primary", use_container_width=True):
            if uploaded_files and folder_name:
                with st.spinner(f"🔍 {len(uploaded_files)}枚の画像を分析中..."):
                    # 画像準備
                    images = []
                    for file in uploaded_files:
                        image = Image.open(file)
                        if image.mode != "RGB":
                            image = image.convert("RGB")
                        images.append(image)

                    # プロンプト構築（短縮版）
                    categories = list(st.session_state.classification_hierarchy.keys())
                    impression_slugs = []
                    for items in st.session_state.impression_tags.values():
                        impression_slugs.extend([item["slug"] for item in items])
                    object_slugs = []
                    for items in st.session_state.object_tags.values():
                        object_slugs.extend([item["slug"] for item in items])

                    prompt = f"""この{len(images)}枚の写真を分析してJSON形式で出力してください。

大分類: {', '.join(categories)}から1つ
印象タグ: {', '.join(impression_slugs[:20])}から最大5つのslugを選択
オブジェクトタグ: {', '.join(object_slugs[:20])}から最大8つのslugを選択

重要: 印象タグとオブジェクトタグは必ず英語のslug（bright, modern, tableなど）で返してください。

例:
{{"大分類": "オフィス", "小項目": "会議室", "印象タグ": ["bright", "modern"], "オブジェクトタグ": ["table", "chair"], "判定理由": "会議室の特徴", "撮影用途": "ビジネスシーン", "特徴": "プロジェクター設置"}}

JSON形式のみで回答してください。"""

                    try:
                        # API呼び出し
                        st.info("🤖 Gemini APIに画像を送信中...")
                        response = model.generate_content(
                            [prompt] + images,
                            generation_config=genai.GenerationConfig(
                                temperature=0.7,
                                max_output_tokens=2048,
                                response_mime_type="application/json"
                            ),
                        )

                        # デバッグ情報を表示
                        st.info("📨 API応答を確認中...")

                        # 応答の基本チェック
                        if not response:
                            st.error("❌ APIから応答がありません")
                            st.stop()

                        if not hasattr(response, "text") or not response.text:
                            st.error("❌ API応答が空です")
                            if hasattr(response, "prompt_feedback"):
                                st.error(
                                    f"プロンプトフィードバック: {response.prompt_feedback}"
                                )
                            st.stop()

                        # 生の応答をデバッグ表示
                        raw_response = response.text.strip()
                        st.info(f"📄 応答の長さ: {len(raw_response)} 文字")

                        with st.expander("🔍 デバッグ: 生のAPI応答"):
                            st.text_area("APIからの応答", raw_response, height=200)

                        # 安全なJSON解析を使用
                        result = parse_classification_response(raw_response)

                        if "error" in result:
                            st.error("AI分析の結果解析に失敗しました")
                            with st.expander("AIの生の応答を確認"):
                                st.text_area(
                                    "応答内容",
                                    result.get("raw_response", ""),
                                    height=300,
                                )
                            st.info("画像を変更するか、再度お試しください。")
                            st.stop()

                        # 結果の後処理
                        result["フォルダ名"] = folder_name
                        result["画像枚数"] = len(images)
                        result["分析日時"] = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                        # セッションステートに保存
                        if "analysis_results" not in st.session_state:
                            st.session_state.analysis_results = []
                        st.session_state.analysis_results.append(result)

                        # データベースに保存
                        try:
                            with sqlite3.connect(db.db_path) as conn:
                                conn.execute(
                                    """
                                    INSERT INTO analysis_history
                                    (folder_name, broad_category, specific_item, impression_tags,
                                     object_tags, reason, purpose, image_count, analyzed_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                    (
                                        folder_name,
                                        result.get("大分類", ""),
                                        result.get("小項目", ""),
                                        json.dumps(
                                            result.get("印象タグ", []),
                                            ensure_ascii=False,
                                        ),
                                        json.dumps(
                                            result.get("オブジェクトタグ", []),
                                            ensure_ascii=False,
                                        ),
                                        result.get("判定理由", ""),
                                        result.get("撮影用途", ""),
                                        len(images),
                                        datetime.now(),
                                    ),
                                )
                            st.success("💾 データベース保存完了")
                        except Exception as db_error:
                            st.warning(f"⚠️ データベース保存エラー: {db_error}")

                        st.success("✅ 分析完了！「分析結果」タブで確認してください")

                        # 結果のプレビュー表示
                        with st.expander("📊 分析結果プレビュー"):
                            st.json(result)

                    except Exception as e:
                        st.error(f"❌ 分析中に予期しないエラーが発生: {e}")
                        st.info("トラブルシューティング:")
                        st.text("- 画像ファイルサイズを小さくしてみてください")
                        st.text("- 画像の枚数を減らしてみてください")
                        st.text("- しばらく時間をおいて再試行してください")

                        # エラーの詳細をログ出力
                        st.text_area("エラー詳細", traceback.format_exc(), height=200)
            else:
                st.warning("⚠️ 物件名と画像を入力してください")

# 分析結果タブ
with tab3:
    st.subheader("📊 最新の分析結果")

    if "analysis_results" in st.session_state and st.session_state.analysis_results:
        latest = st.session_state.analysis_results[-1]

        # メトリクス表示
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("大分類", latest.get("大分類", "不明"))
        with col2:
            st.metric("小項目", latest.get("小項目", "不明"))
        with col3:
            st.metric("画像数", latest.get("画像枚数", 0))
        with col4:
            st.metric("撮影用途", latest.get("撮影用途", "汎用"))

        # タグの視覚的表示
        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 🎨 印象タグ")
            impression_html = '<div class="tag-container">'
            for slug in latest.get("印象タグ", []):
                # slugからラベルを検索
                for category, items in st.session_state.impression_tags.items():
                    for item in items:
                        if item["slug"] == slug:
                            impression_html += f'<span class="tag-badge impression-tag">{item["label"]}</span>'
            impression_html += "</div>"
            st.markdown(impression_html, unsafe_allow_html=True)

        with col2:
            st.markdown("### 🔧 オブジェクトタグ")
            object_html = '<div class="tag-container">'
            for slug in latest.get("オブジェクトタグ", []):
                # slugからラベルを検索
                for category, items in st.session_state.object_tags.items():
                    for item in items:
                        if item["slug"] == slug:
                            object_html += f'<span class="tag-badge object-tag">{item["label"]}</span>'
            object_html += "</div>"
            st.markdown(object_html, unsafe_allow_html=True)

        # 詳細情報
        st.divider()
        st.info(f"💡 **判定理由**: {latest.get('判定理由', '不明')}")
        st.info(f"✨ **特徴**: {latest.get('特徴', '不明')}")

        # JSON表示
        with st.expander("🔍 詳細データ (JSON)"):
            st.json(latest)
    else:
        st.info("まだ分析結果がありません")

# 統計タブ
with tab4:
    st.subheader("📈 統計情報")

    try:
        with sqlite3.connect(db.db_path) as conn:
            # カテゴリ別集計
            stats = conn.execute(
                """
                SELECT broad_category, COUNT(*) as count
                FROM analysis_history
                WHERE broad_category IS NOT NULL AND broad_category != ''
                GROUP BY broad_category
                ORDER BY count DESC
            """
            ).fetchall()

            if stats:
                st.markdown("### カテゴリ別集計")

                # メトリクスで表示
                cols = st.columns(min(len(stats), 4))
                for i, (cat, count) in enumerate(stats):
                    if cat:  # カテゴリ名が空でない場合のみ表示
                        cols[i % len(cols)].metric(cat, f"{count}件")

                # 最近の分析履歴
                st.divider()
                st.markdown("### 最近の分析履歴")

                recent = conn.execute(
                    """
                    SELECT folder_name, broad_category, specific_item, analyzed_at
                    FROM analysis_history
                    WHERE folder_name IS NOT NULL
                    ORDER BY analyzed_at DESC
                    LIMIT 10
                """
                ).fetchall()

                if recent:
                    for record in recent:
                        # 安全にレコードにアクセス
                        folder_name = (
                            record[0] if len(record) > 0 and record[0] else "不明"
                        )
                        broad_category = (
                            record[1] if len(record) > 1 and record[1] else "不明"
                        )
                        specific_item = (
                            record[2] if len(record) > 2 and record[2] else "不明"
                        )
                        analyzed_at = (
                            record[3] if len(record) > 3 and record[3] else "不明"
                        )

                        # 日時の安全な切り取り
                        date_str = (
                            analyzed_at[:16]
                            if isinstance(analyzed_at, str) and len(analyzed_at) >= 16
                            else str(analyzed_at)
                        )

                        st.text(
                            f"📁 {folder_name} - {broad_category}/{specific_item} ({date_str})"
                        )
                else:
                    st.info("分析履歴がありません")

                # データベーステーブル情報の表示（デバッグ用）
                with st.expander("🔍 データベース情報"):
                    # テーブル構造を確認
                    table_info = conn.execute(
                        "PRAGMA table_info(analysis_history)"
                    ).fetchall()
                    st.text("analysis_history テーブル構造:")
                    for col in table_info:
                        st.text(f"  {col[1]} ({col[2]})")

                    # 総レコード数
                    total_count = conn.execute(
                        "SELECT COUNT(*) FROM analysis_history"
                    ).fetchone()[0]
                    st.metric("総分析数", total_count)

            else:
                st.info("まだデータがありません")

                # 空のテーブルでも構造を表示
                with st.expander("🔍 データベース情報"):
                    table_info = conn.execute(
                        "PRAGMA table_info(analysis_history)"
                    ).fetchall()
                    if table_info:
                        st.text("analysis_history テーブル構造:")
                        for col in table_info:
                            st.text(f"  {col[1]} ({col[2]})")
                    else:
                        st.text("テーブルが見つかりません")

    except Exception as e:
        st.error(f"データベースエラー: {e}")
        st.text_area("エラー詳細", traceback.format_exc(), height=200)

# フッター
st.divider()
st.caption("スタジオ物件分類システム v2.0 - 階層型タグ管理・SQLite対応・エラー対策版")
ENDOFFILE

echo "✅ 修正版ファイルを作成しました: streamlit_app/streamlit_classifier_sqlite_fixed.py"
echo ""
echo "起動コマンド:"
echo "streamlit run streamlit_app/streamlit_classifier_sqlite_fixed.py"
