# ✅ Streamlit UI対応：SEO記事作成エージェント（OpenAI Assistant API + Tools）＋カテゴリ・タグ自動作成＋アイキャッチ自動設定

import openai
import requests
import streamlit as st
from requests.auth import HTTPBasicAuth
import time
import markdown
from bs4 import BeautifulSoup

# --- APIキー・環境設定 ---
OPENAI_API_KEY = "your_openai_api_key"
openai.api_key = OPENAI_API_KEY

# --- WordPress設定 ---
WP_BASE_URL = "https://yourdomain.com"
WP_API_URL = WP_BASE_URL + "/wp-json/wp/v2/posts"
WP_USERNAME = "your_wp_user"
WP_APP_PASSWORD = "your_app_password"

# --- カテゴリとタグを作成または取得 ---
def get_or_create_term(name, term_type):
    url = f"{WP_BASE_URL}/wp-json/wp/v2/{term_type}s"
    auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    res = requests.get(url, params={"search": name}, auth=auth)
    if res.status_code == 200:
        items = res.json()
        for item in items:
            if item["name"] == name:
                return item["id"]
    res = requests.post(url, json={"name": name}, auth=auth)
    if res.status_code == 201:
        return res.json()["id"]
    else:
        st.error(f"{term_type}作成失敗: {res.text}")
        return None

# --- アイキャッチ画像を本文中から取得・アップロード ---
def extract_and_upload_featured_image(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    first_img = soup.find("img")
    if not first_img:
        return None
    image_url = first_img.get("src")
    if not image_url:
        return None

    media_url = WP_BASE_URL + "/wp-json/wp/v2/media"
    img_data = requests.get(image_url).content
    headers = {
        "Content-Disposition": "attachment; filename=featured.jpg",
        "Content-Type": "image/jpeg"
    }
    res = requests.post(
        media_url,
        headers=headers,
        data=img_data,
        auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    )
    if res.status_code == 201:
        return res.json()["id"]
    else:
        st.warning("⚠️ アイキャッチ画像のアップロードに失敗しました")
        return None

# --- GPTでカテゴリとタグを推定 ---
def suggest_categories_and_tags(markdown_text):
    prompt = f"""
以下のMarkdown記事から、WordPress投稿に適したカテゴリ（1つ）とタグ（3つ以内）を日本語で提案してください。
カテゴリとタグは汎用的なブログで使える範囲にしてください。

記事内容:
{markdown_text}

フォーマット:
カテゴリ: <カテゴリ名>
タグ: ["タグ1", "タグ2", "タグ3"]
"""
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    text = response["choices"][0]["message"]["content"]
    category = "ブログ"
    tags = []
    for line in text.splitlines():
        if line.startswith("カテゴリ:"):
            category = line.split(":", 1)[1].strip()
        elif line.startswith("タグ:"):
            tags = eval(line.split(":", 1)[1].strip())
    return category, tags

# --- WordPress投稿関数 ---
def publish_to_wordpress(title, html_content, category, tags):
    cat_id = get_or_create_term(category, "categorie")
    tag_ids = [get_or_create_term(tag, "tag") for tag in tags]
    tag_ids = [tid for tid in tag_ids if tid is not None]
    featured_media_id = extract_and_upload_featured_image(html_content)

    post_data = {
        "title": title,
        "content": html_content,
        "status": "publish",
        "categories": [cat_id] if cat_id else [],
        "tags": tag_ids
    }
    if featured_media_id:
        post_data["featured_media"] = featured_media_id

    res = requests.post(
        WP_API_URL,
        json=post_data,
        auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    )
    if res.status_code == 201:
        return res.json().get("link")
    else:
        st.error(f"❌ 投稿失敗: {res.status_code}")
        st.code(res.text)
        return None

# --- スレッド＆ラン実行関数 ---
def run_agent_interaction(assistant_id, keyword, persona):
    thread = openai.beta.threads.create()

    user_message = f"以下のキーワードで記事を作成してください：\nキーワード: {keyword}\nペルソナ: {persona}"
    openai.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_message
    )

    run = openai.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
        instructions="SEO記事を生成し、商品・画像を挿入し、WordPressに投稿してください。"
    )

    with st.spinner("🕐 実行中..."):
        while True:
            run_status = openai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if run_status.status in ["completed", "failed", "cancelled"]:
                break
            time.sleep(2)

    messages = openai.beta.threads.messages.list(thread_id=thread.id)
    for msg in reversed(messages.data):
        if msg.role == "assistant":
            return msg.content[0].text.value

    return "❌ 結果を取得できませんでした"

# --- Streamlit UI ---
def main():
    st.title("📝 SEO記事作成エージェント（OpenAI Agents SDK）")

    assistant_id = st.text_input("Assistant ID", value="your_assistant_id")
    keyword = st.text_input("メインキーワード", value="プログラミング 独学")
    persona = st.text_input("読者ペルソナ", value="初心者エンジニア志望")

    if "markdown_article" not in st.session_state:
        st.session_state.markdown_article = ""
        st.session_state.html_preview = ""
        st.session_state.published_url = None

    if st.button("記事を生成する"):
        if not assistant_id or not keyword:
            st.warning("Assistant IDとキーワードは必須です。")
        else:
            result = run_agent_interaction(assistant_id, keyword, persona)
            st.session_state.markdown_article = result
            st.session_state.html_preview = markdown.markdown(result)
            st.session_state.published_url = None

    if st.session_state.markdown_article:
        st.subheader("📝 Markdown出力")
        st.code(st.session_state.markdown_article, language="markdown")

        st.subheader("🌐 HTMLプレビュー")
        st.components.v1.html(st.session_state.html_preview, height=600, scrolling=True)

        if st.button("WordPressに投稿する"):
            soup = BeautifulSoup(st.session_state.html_preview, "html.parser")
            title = soup.find("h1").text if soup.find("h1") else keyword
            category, tags = suggest_categories_and_tags(st.session_state.markdown_article)
            link = publish_to_wordpress(title, st.session_state.html_preview, category, tags)
            if link:
                st.session_state.published_url = link

    if st.session_state.published_url:
        st.success("✅ WordPressに投稿されました！")
        st.markdown(f"[👉 投稿を確認する]({st.session_state.published_url})")

if __name__ == "__main__":
    main()
