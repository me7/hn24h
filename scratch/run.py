# /// script
# dependencies = [
#   "requests",
#   "beautifulsoup4",
#   "google-generativeai",
# ]
# ///

import os
import sys
import json
import time
import sqlite3
import glob
import argparse
import subprocess
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ป้องกันปัญหาแสดงผลภาษาไทยใน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# กำหนดชื่อฐานข้อมูลและรุ่นโมเดล
DB_NAME = "hn_knowledge_base.db"
MODEL_NAME = "gemini-2.5-flash"

# =====================================================================
# 1. ระบบฐานข้อมูล (Database Module)
# =====================================================================

def init_db():
    """
    สร้างฐานข้อมูลและตารางสำหรับเก็บข้อมูลคลังความรู้
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # ตารางหลักเก็บข้อมูลข่าวสารและเนื้อหาดิบพร้อมบทสรุป
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT,
        hn_url TEXT,
        points INTEGER,
        num_comments INTEGER,
        author TEXT,
        article_text TEXT,
        comments_text TEXT,
        teaser TEXT,
        article_summary TEXT,
        comments_summary TEXT,
        fetched_date TEXT NOT NULL
    );
    """)
    
    # ตารางเก็บแท็กจัดหมวดหมู่
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    """)
    
    # ตารางเชื่อมโยง Many-to-Many
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_tags (
        story_id TEXT,
        tag_id INTEGER,
        PRIMARY KEY (story_id, tag_id),
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
    );
    """)
    
    conn.commit()
    conn.close()

# =====================================================================
# 2. ระบบดึงข้อมูล (Fetch Module)
# =====================================================================

def get_hn_stories(points_threshold=150, max_stories=40):
    """
    ดึงรายชื่อข่าวยอดนิยมจาก Hacker News ในรอบ 24 ชั่วโมงที่ผ่านมา
    """
    print("กำลังคำนวณเวลา 24 ชั่วโมงย้อนหลัง...")
    time_24h_ago = int((datetime.utcnow() - timedelta(hours=24)).timestamp())
    
    stories = []
    page = 0
    max_pages = 5
    
    print("กำลังเริ่มดึงรายชื่อข่าวจาก Algolia HN API (หน้า 0-4)...")
    while page < max_pages:
        url = f"https://hn.algolia.com/api/v1/search?tags=story&numericFilters=created_at_i>{time_24h_ago}&page={page}&hitsPerPage=50"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            hits = data.get("hits", [])
            if not hits:
                break
            
            for hit in hits:
                points = hit.get("points", 0)
                story_id = hit.get("objectID")
                title = hit.get("title")
                story_url = hit.get("url")
                num_comments = hit.get("num_comments", 0)
                author = hit.get("author")
                
                hn_url = f"https://news.ycombinator.com/item?id={story_id}"
                if not story_url:
                    story_url = hn_url
                
                stories.append({
                    "id": story_id,
                    "title": title,
                    "url": story_url,
                    "hn_url": hn_url,
                    "points": points,
                    "num_comments": num_comments,
                    "author": author,
                    "created_at": hit.get("created_at")
                })
            page += 1
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงข้อมูลหน้า {page}: {e}")
            break
            
    stories.sort(key=lambda x: x["points"], reverse=True)
    filtered_stories = [s for s in stories if s["points"] >= points_threshold]
    
    if len(filtered_stories) < 15 and len(stories) > 0:
        filtered_stories = stories[:max(15, len(stories))]
        
    final_stories = filtered_stories[:max_stories]
    print(f"ดึงรายชื่อข่าวเรียบร้อย: พบข่าวผ่านเกณฑ์ทั้งหมด {len(final_stories)} ข่าว")
    return final_stories

def scrape_article_content(url):
    """
    ดาวน์โหลดและดึงเนื้อหาข้อความที่เป็นประโยชน์จากเว็บบทความข่าว
    """
    if "news.ycombinator.com" in url:
        return "บทความนี้เป็นกระทู้พูดคุยบน Hacker News โดยตรง ไม่มีหน้าเว็บภายนอก"
        
    print(f"กำลังดึงเนื้อหาบทความ: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"ไม่สามารถเข้าถึงหน้าเว็บได้ (HTTP Error {response.status_code})"
            
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "iframe"]):
            tag.decompose()
            
        main_content = soup.find("article") or soup.find("main") or soup.find("div", class_="content") or soup.body
        if not main_content:
            main_content = soup
            
        paragraphs = main_content.find_all(["p", "li"])
        text_lines = []
        for p in paragraphs:
            text = p.get_text().strip()
            if len(text) > 20:
                text_lines.append(text)
                
        full_text = "\n\n".join(text_lines)
        if len(full_text) > 8000:
            full_text = full_text[:8000] + "\n\n...[เนื้อหาถูกตัดเนื่องจากยาวเกินไป]..."
            
        return full_text if full_text.strip() else "ไม่พบเนื้อหาข้อความยาวในหน้าเว็บนี้"
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการดึงข้อมูลหน้าเว็บ: {str(e)}"

def format_comments(comments_list, depth=0, max_comments=15, count=0):
    """
    แปลงความคิดเห็นในบอร์ดให้เรียบง่าย
    """
    text = ""
    for c in comments_list:
        if count >= max_comments:
            break
        author = c.get("author") or "anonymous"
        comment_html = c.get("text") or ""
        if not comment_html:
            continue
            
        soup = BeautifulSoup(comment_html, "html.parser")
        comment_text = soup.get_text(separator=" ").strip()
        comment_text = " ".join(comment_text.split())
        
        indent = "  " * depth
        text += f"{indent}- [{author}]: {comment_text}\n\n"
        count += 1
        
        if c.get("children"):
            child_text, count = format_comments(c["children"], depth + 1, max_comments, count)
            text += child_text
            
    return text, count

def fetch_hn_comments(story_id):
    """
    ดึงความคิดเห็นทั้งหมดของกระทู้นั้นๆ
    """
    print(f"กำลังดึงความคิดเห็นสำหรับกระทู้ ID: {story_id}")
    url = f"https://hn.algolia.com/api/v1/items/{story_id}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        children = data.get("children", [])
        
        formatted_text, _ = format_comments(children, depth=0, max_comments=15)
        if len(formatted_text) > 5000:
            formatted_text = formatted_text[:5000] + "\n\n...[ความคิดเห็นเพิ่มเติมถูกละไว้]..."
        return formatted_text if formatted_text.strip() else "ไม่มีความคิดเห็นในกระทู้นี้"
    except Exception as e:
        return f"ไม่สามารถดึงข้อมูลความคิดเห็นได้: {str(e)}"

def run_fetch_phase():
    """
    รันกระบวนการดึงข้อมูลทั้งหมดและเซฟลง SQLite
    """
    print("=== เริ่มขั้นตอนดึงข้อมูลข่าวสารประจำวัน ===")
    init_db()
    
    stories = get_hn_stories(points_threshold=150, max_stories=40)
    if not stories:
        print("ไม่พบข่าวผ่านเกณฑ์คะแนน")
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for i, story in enumerate(stories, 1):
        print(f"\n--- ประมวลผลข่าว {i}/{len(stories)}: {story['title']} ---")
        
        if "item?id=" in story["url"]:
            article_text = "บทความนี้เป็นกระทู้พูดคุยบน Hacker News โดยตรง ไม่มีหน้าเว็บภายนอก"
        else:
            article_text = scrape_article_content(story["url"])
            
        comments_text = fetch_hn_comments(story["id"])
        
        cursor.execute("""
        INSERT OR IGNORE INTO stories (id, title, fetched_date) VALUES (?, ?, ?);
        """, (story["id"], story["title"], today_str))
        
        cursor.execute("""
        UPDATE stories SET
            title = ?,
            url = ?,
            hn_url = ?,
            points = ?,
            num_comments = ?,
            author = ?,
            article_text = ?,
            comments_text = ?,
            fetched_date = ?
        WHERE id = ?;
        """, (
            story["title"],
            story["url"],
            story["hn_url"],
            story["points"],
            story["num_comments"],
            story["author"],
            article_text,
            comments_text,
            today_str,
            story["id"]
        ))
        
        time.sleep(0.5)
        
    conn.commit()
    conn.close()
    print(f"\n=== เสร็จสิ้นการดึงข้อมูลข่าวสาร: บันทึกข่าวสาร {len(stories)} ลงฐานข้อมูลสำเร็จ ===")

# =====================================================================
# 3. ระบบสรุปข้อมูลอัตโนมัติ (AI Summarizer Module)
# =====================================================================

def get_summaries_from_ai(model, title, article_text, comments_text):
    """
    ส่งข่าวไปสรุปด้วย AI ผ่าน Gemini API
    """
    import google.generativeai as genai
    prompt = f"""
คุณเป็นผู้เชี่ยวชาญด้านข่าวเทคโนโลยีและนักแปลสรุปภาษาไทยชั้นนำ หน้าที่ของคุณคืออ่านบทความและคอมเมนต์ในกระทู้ Hacker News ด้านล่างนี้ แล้วสรุปวิเคราะห์ข้อมูลเชิงลึกเป็นภาษาไทยตามสเปกและตัวอย่างที่กำหนด

[สเปกข่าว]
หัวข้อข่าวอังกฤษ: "{title}"
เนื้อหาข้อความดิบ: {article_text[:6000]}
ความคิดเห็นดิบในบอร์ด: {comments_text[:4000]}

---
[ข้อตกลงและสไตล์เอาต์พุต]
1. ภาษา: ตอบเป็นภาษาไทยที่สุภาพ เป็นทางการ และมีความลื่นไหลเป็นธรรมชาติตามตัวอย่างด้านล่าง
2. ห้ามใช้ตัวหนังสือย่อหรือสรุปสั้นเกินไป ให้ใช้รายละเอียดและข้อมูลเชิงลึกเพื่อการศึกษา
3. ผลลัพธ์ต้องส่งกลับมาในรูปแบบอ็อบเจกต์ JSON ที่มี 3 คีย์ดังนี้ (ส่งกลับเฉพาะตัวอ็อบเจกต์ JSON เท่านั้น ห้ามเขียนคำเกริ่นหรือส่งโค้ดบล็อกอ้อม):
{{
  "teaser": "สรุปเนื้อหาข่าวสารเป็นประโยคสั้นๆ 1 ประโยคเพื่อดึงดูดสายตา",
  "article_summary": "เขียนสรุปรายละเอียดเนื้อหาของข่าวเป็นย่อหน้าและหัวข้อย่อยโดยใช้แท็ก HTML เช่น <p>, <ul>, <li>, <strong> เพื่อความสวยงาม โดยแบ่งเป็นจุดเด่นสำคัญอย่างละเอียด",
  "comments_summary": "เขียนสรุปประเด็นดราม่า ข้อถกเถียง มุมมองเชิงบวก/ลบ และข้อสรุปของเหล่านักพัฒนาในบอร์ด HN เป็นหัวข้อย่อยโดยใช้แท็ก HTML สวยงาม"
}}

---
[ตัวอย่างผลลัพธ์คุณภาพสูงที่คุณต้องเลียนแบบสไตล์]
{{
  "teaser": "Gooey คือ Framework สำหรับพัฒนา User Interface (UI) ที่เน้นประสิทธิภาพสูงโดยใช้ GPU สำหรับภาษา Zig โดยเฉพาะครับ",
  "article_summary": "<p>Gooey เป็นเฟรมเวิร์กสร้างส่วนประสานงานผู้ใช้ (GUI) ยุคใหม่ที่ออกแบบมาสำหรับภาษายอดนิยมอย่าง Zig โดยเน้นประสิทธิภาพและความเบาบางของชิ้นส่วนระบบ จุดเด่นสำคัญมีดังนี้ครับ:</p><ul><li><strong>เน้นประสิทธิภาพ:</strong> ใช้การเรนเดอร์ผ่าน GPU โดยรองรับ Metal บน macOS, Vulkan บน Linux...</li></ul>",
  "comments_summary": "<p>กระทู้บน Hacker News (HN) เกี่ยวกับ Gooey เผยให้เห็นประเด็นดราม่าและมุมมองที่น่าสนใจจากฝั่งนักพัฒนาอย่างดุเดือดครับ โดยเสียงสะท้อนส่วนใหญ่เปลี่ยนจากความตื่นเต้นในตอนแรก กลายเป็นความกังวลและผิดหวัง...</p><ul><li><strong>1. จุดชนวนดราม่า: เมื่อโปรเจกต์ดาวรุ่งกลายเป็นงาน AI (Slop)</strong><br>สิ่งที่ทำให้นักพัฒนาสะดุดตาที่สุดคือ โปรเจกต์นี้ขับเคลื่อนด้วย AI เกือบทั้งหมด...</li></ul>"
}}
"""
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text.strip())
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการส่งข้อมูลไปสรุปผ่าน Gemini API: {e}")
        return None

def run_ai_summarizer_phase():
    """
    รันประมวลผลสรุปข่าวอัจฉริยะผ่าน Gemini API (ถ้ามีคีย์)
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ข้ามขั้นตอน AI Auto-Summarize: ไม่พบการตั้งค่า GEMINI_API_KEY (หากทำงานผ่าน Antigravity 2 ขั้นตอนนี้จะข้ามไปและให้เอเจนต์สรุปผ่านห้องแชตแทน)")
        return
        
    print("=== เริ่มขั้นตอนประมวลผลสรุปด้วย AI ผ่าน Gemini API ===")
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("""
    SELECT id, title, article_text, comments_text 
    FROM stories 
    WHERE fetched_date = ? AND (teaser IS NULL OR teaser = '' OR teaser = title);
    """, (today_str,))
    pending_stories = cursor.fetchall()
    
    if not pending_stories:
        print("ไม่มีข่าวสารค้างการสรุปในวันนี้")
        conn.close()
        return
        
    print(f"พบข่าวที่ค้างการสรุป {len(pending_stories)} ข่าว")
    for s_id, title, art_text, comm_text in pending_stories:
        print(f"-> ส่งสรุปข่าวด้วย AI: {title}")
        ai_res = get_summaries_from_ai(model, title, art_text, comm_text)
        if ai_res:
            teaser = ai_res.get("teaser", title)
            art_sum = ai_res.get("article_summary", "")
            comm_sum = ai_res.get("comments_summary", "")
            
            cursor.execute("""
            UPDATE stories SET
                teaser = ?,
                article_summary = ?,
                comments_summary = ?
            WHERE id = ?;
            """, (teaser, art_sum, comm_sum, s_id))
            
            # ติดแท็กจัดหมวดหมู่อัตโนมัติจากคำศัพท์ในหัวข้อข่าว
            tags_to_add = []
            title_lower = title.lower()
            for key_tag in ["zig", "rust", "ai", "apple", "macbook", "linux", "gpu", "security", "database", "git", "web", "elixir"]:
                if key_tag in title_lower:
                    tags_to_add.append(key_tag)
            
            for tag_name in tags_to_add:
                cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?);", (tag_name,))
                cursor.execute("SELECT id FROM tags WHERE name = ?;", (tag_name,))
                tag_id = cursor.fetchone()[0]
                cursor.execute("INSERT OR IGNORE INTO story_tags (story_id, tag_id) VALUES (?, ?);", (s_id, tag_id))
            conn.commit()
            
    conn.close()
    print("=== เสร็จสิ้นการทำงานของเฟส AI Summarizer ===")

# =====================================================================
# 4. ระบบสร้างหน้า HTML และพุชขึ้น GitHub (Build Module)
# =====================================================================

def format_thai_date(date_str=None):
    """
    แปลงวันที่ให้อยู่ในฟอร์แมตภาษาไทย
    """
    months_th = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    if date_str:
        try:
            dt = datetime.strptime(date_str.split('T')[0], "%Y-%m-%d")
        except:
            dt = datetime.now()
    else:
        dt = datetime.now()
    year_th = dt.year + 543
    return f"{dt.day} {months_th[dt.month - 1]} {year_th}"

def build_index_page(conn):
    """
    สร้างหน้าแรก index.html เป็นแดชบอร์ดปฏิทินข่าวสำหรับเปิดเลือกอ่านย้อนหลัง
    """
    cursor = conn.cursor()
    cursor.execute("""
    SELECT DISTINCT fetched_date 
    FROM stories 
    WHERE teaser IS NOT NULL AND teaser != ''
    ORDER BY fetched_date DESC;
    """)
    dates = [row[0] for row in cursor.fetchall()]
    
    if not dates:
        print("Warning: ไม่มีข้อมูลสรุปในคลังเพื่อสร้างสารบัญ index.html")
        return
        
    html_content = """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hacker News Daily Archive - คลังสรุปข่าวสารประจำวัน</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 29, 49, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-color: #f97316;
            --accent-hover: #ea580c;
            --shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
            --font-display: 'Outfit', 'Sarabun', sans-serif;
            --font-sans: 'Inter', 'Sarabun', sans-serif;
        }

        body {
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(249, 115, 22, 0.07) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(99, 102, 241, 0.07) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            font-family: var(--font-sans);
            margin: 0;
            padding: 0;
            font-size: 18px;
            line-height: 1.75;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
        }

        header {
            text-align: center;
            margin-bottom: 50px;
        }

        h1 {
            font-family: var(--font-display);
            font-size: 2.8rem;
            font-weight: 700;
            margin: 0 0 12px 0;
            background: linear-gradient(to right, #f97316, #fb923c, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1.25rem;
            margin: 0;
        }

        .archive-list {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .archive-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            box-shadow: var(--shadow);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .archive-card:hover {
            border-color: rgba(249, 115, 22, 0.35);
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(249, 115, 22, 0.07);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 10px;
        }

        .archive-date {
            font-family: var(--font-display);
            font-size: 1.4rem;
            font-weight: 600;
            color: var(--accent-color);
            margin: 0;
        }

        .top-news-title {
            font-size: 0.95rem;
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin: 8px 0 4px 0;
        }

        .news-bullets {
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .news-bullets li {
            font-size: 1.05rem;
            color: #cbd5e1;
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }

        .news-bullets li::before {
            content: "•";
            color: var(--accent-color);
            font-weight: bold;
        }

        .action-btn {
            font-size: 0.95rem;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.2s ease;
            background: rgba(249, 115, 22, 0.1);
            border: 1px solid rgba(249, 115, 22, 0.25);
            color: var(--accent-color);
            align-self: flex-start;
            margin-top: 10px;
        }

        .action-btn:hover {
            background: var(--accent-color);
            color: white;
        }

        footer.page-footer {
            text-align: center;
            margin-top: 70px;
            padding-top: 30px;
            border-top: 1px solid var(--card-border);
            font-size: 0.95rem;
            color: var(--text-secondary);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Hacker News Digest</h1>
            <p class="subtitle">คลังสะสมบทสรุปข่าวและประเด็นสนทนา Hacker News ภาษาไทยประจำวัน</p>
        </header>
        <main class="archive-list">
"""

    for date_str in dates:
        date_formatted = format_thai_date(date_str)
        filename = f"HN_{date_str.replace('-', '')}.html"
        
        cursor.execute("""
        SELECT title, points 
        FROM stories 
        WHERE fetched_date = ? 
        ORDER BY points DESC 
        LIMIT 3;
        """, (date_str,))
        top_news = cursor.fetchall()
        
        bullets_html = ""
        if top_news:
            bullets_html += '<div class="top-news-title">ข่าวเด่นวันนี้:</div>'
            bullets_html += '<ul class="news-bullets">'
            for title, pts in top_news:
                bullets_html += f'<li>{title} ({pts} pts)</li>'
            bullets_html += '</ul>'
            
        html_content += f"""
            <!-- ARCHIVE FOR {date_str} -->
            <div class="archive-card">
                <div class="card-header">
                    <h2 class="archive-date">📅 {date_formatted}</h2>
                </div>
                {bullets_html}
                <a href="./{filename}" class="action-btn">เปิดอ่านสรุปข่าวประจำวัน</a>
            </div>
        """
        
    html_content += """
        </main>
        <footer class="page-footer">
            <p>Hacker News Daily Digest • ออกแบบและโฮสต์บน GitHub Pages สำหรับอ่านบนโทรศัพท์มือถือ</p>
        </footer>
    </div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("สร้างหน้าสารบัญความรู้ 'index.html' ตัวใหม่เรียบร้อยแล้ว!")

def run_build_phase():
    """
    ดึงบทสรุปจาก SQLite และจัดทำไฟล์เว็บและอัปเดต Git
    """
    print("=== เริ่มขั้นตอนประกอบร่างเว็บ HTML ===")
    
    # 1. ย้ายบทสรุปตกค้างใน JSON ลงฐานข้อมูล (หากมีหลงเหลือจากการประมวลผลภายนอก)
    if os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        json_summaries = {}
        if os.path.exists("hn_summaries.json"):
            try:
                with open("hn_summaries.json", "r", encoding="utf-8") as f:
                    json_summaries.update(json.load(f))
            except Exception as e:
                print(f"Warning: โหลดไฟล์หลัก hn_summaries.json ไม่สำเร็จ: {e}")
                
        for file_path in glob.glob("hn_summaries_*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    json_summaries.update(json.load(f))
            except Exception as e:
                print(f"Warning: เกิดข้อผิดพลาดในการโหลดไฟล์ย่อย {file_path}: {e}")
                
        if json_summaries:
            print(f"พบข้อมูลสรุปใน JSON ทั้งหมด {len(json_summaries)} ข่าว กำลังเขียนทับลงฐานข้อมูล...")
            for story_id, data in json_summaries.items():
                teaser = data.get("teaser", "")
                art_sum = data.get("article_summary", "")
                comm_sum = data.get("comments_summary", "")
                cursor.execute("""
                UPDATE stories SET
                    teaser = ?,
                    article_summary = ?,
                    comments_summary = ?
                WHERE id = ?;
                """, (teaser, art_sum, comm_sum, story_id))
            conn.commit()
        conn.close()

    # 2. ดึงข้อมูลประมวลผล HTML
    if not os.path.exists(DB_NAME):
        print(f"Error: ไม่พบฐานข้อมูล '{DB_NAME}'")
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT MAX(fetched_date) FROM stories;")
    latest_date = cursor.fetchone()[0]
    if not latest_date:
        print("ไม่มีข้อมูลข่าวสารในระบบ")
        conn.close()
        return
        
    print(f"กำลังดึงข้อมูลสำหรับวันที่ล่าสุดที่มีข้อมูล: {latest_date}")
    cursor.execute("""
    SELECT id, title, url, hn_url, points, num_comments, author, article_text, comments_text, teaser, article_summary, comments_summary
    FROM stories
    WHERE fetched_date = ?
    ORDER BY points DESC;
    """, (latest_date,))
    rows = cursor.fetchall()
    
    raw_stories = []
    summaries = {}
    for row in rows:
        s_id, title, url, hn_url, points, num_comments, author, art_text, comm_text, teaser, art_sum, comm_sum = row
        raw_stories.append({
            "id": s_id, "title": title, "url": url, "hn_url": hn_url, "points": points, "num_comments": num_comments, "author": author
        })
        summaries[s_id] = {
            "teaser": teaser if teaser else title,
            "article_summary": art_sum if art_sum else "",
            "comments_summary": comm_sum if comm_sum else ""
        }
        
    today_str = latest_date.replace("-", "")
    html_filename = f"HN_{today_str}.html"
    thai_date = format_thai_date(latest_date)
    
    # ดีไซน์และโครงสร้าง HTML สไตล์พรีเมียมตัวอักษรใหญ่
    html_content = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hacker News สรุปข่าวเด่นประจำวัน - {thai_date}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 29, 49, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-color: #f97316;
            --accent-hover: #ea580c;
            --badge-bg: rgba(249, 115, 22, 0.1);
            --shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
            --font-display: 'Outfit', 'Sarabun', sans-serif;
            --font-sans: 'Inter', 'Sarabun', sans-serif;
        }}

        body {{
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(249, 115, 22, 0.07) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(99, 102, 241, 0.07) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            font-family: var(--font-sans);
            margin: 0;
            padding: 0;
            font-size: 18px;
            line-height: 1.75;
        }}

        .container {{
            max-width: 950px;
            margin: 0 auto;
            padding: 40px 20px;
        }}

        header {{
            text-align: center;
            margin-bottom: 50px;
        }}

        h1 {{
            font-family: var(--font-display);
            font-size: 2.8rem;
            font-weight: 700;
            margin: 0 0 12px 0;
            background: linear-gradient(to right, #f97316, #fb923c, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .date-badge {{
            display: inline-block;
            padding: 6px 20px;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            font-size: 1.05rem;
            color: var(--text-secondary);
            margin-bottom: 20px;
            font-weight: 600;
        }}

        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.25rem;
            margin: 0;
        }}

        .news-list {{
            display: flex;
            flex-direction: column;
            gap: 28px;
        }}

        .news-item {{
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 26px;
            box-shadow: var(--shadow);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .news-item:hover {{
            border-color: rgba(249, 115, 22, 0.35);
            box-shadow: 0 10px 30px rgba(249, 115, 22, 0.07);
            transform: translateY(-2px);
        }}

        details {{
            width: 100%;
        }}

        summary {{
            list-style: none;
            outline: none;
            cursor: pointer;
        }}

        summary::-webkit-details-marker {{
            display: none;
        }}

        .summary-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 18px;
        }}

        .summary-title-section {{
            flex-grow: 1;
        }}

        .story-title {{
            font-family: var(--font-display);
            font-size: 1.45rem;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0 0 10px 0;
            line-height: 1.4;
            transition: color 0.2s ease;
        }}

        .story-title:hover {{
            color: var(--accent-color);
        }}

        .teaser {{
            font-size: 1.15rem;
            color: var(--text-secondary);
            margin: 0 0 18px 0;
            font-weight: 400;
        }}

        .meta-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            align-items: center;
        }}

        .badge {{
            font-size: 0.85rem;
            padding: 5px 12px;
            border-radius: 8px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.05);
            color: var(--text-secondary);
        }}

        .badge-points {{
            background: var(--badge-bg);
            border-color: rgba(249, 115, 22, 0.25);
            color: var(--accent-color);
        }}

        .badge-comments {{
            background: rgba(99, 102, 241, 0.1);
            border-color: rgba(99, 102, 241, 0.25);
            color: #818cf8;
        }}

        .badge-domain {{
            text-transform: lowercase;
            max-width: 220px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .toggle-icon {{
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--card-border);
            color: var(--text-secondary);
            transition: all 0.3s ease;
            font-size: 0.9rem;
        }}

        details[open] .toggle-icon {{
            transform: rotate(180deg);
            background: var(--badge-bg);
            border-color: rgba(249, 115, 22, 0.3);
            color: var(--accent-color);
        }}

        .details-content {{
            margin-top: 26px;
            padding-top: 26px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            display: grid;
            grid-template-columns: 1fr;
            gap: 26px;
            animation: fadeIn 0.4s ease-out;
        }}

        @media (min-width: 800px) {{
            .details-content {{
                grid-template-columns: 1fr 1fr;
            }}
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .content-section {{
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            padding: 22px;
        }}

        .section-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 1.25rem;
            font-weight: 600;
            margin: 0 0 18px 0;
            font-family: var(--font-display);
        }}

        .section-header-article {{
            color: #fb923c;
        }}

        .section-header-discussion {{
            color: #818cf8;
        }}

        .section-body {{
            font-size: 1.08rem;
            color: #cbd5e1;
            margin: 0;
        }}

        .section-body p {{
            margin: 0 0 14px 0;
        }}

        .section-body p:last-child {{
            margin-bottom: 0;
        }}

        .section-body ul {{
            margin: 0;
            padding-left: 24px;
        }}

        .section-body li {{
            margin-bottom: 10px;
        }}

        .section-body li:last-child {{
            margin-bottom: 0;
        }}

        .links-row {{
            grid-column: 1 / -1;
            display: flex;
            gap: 16px;
            margin-top: 14px;
        }}

        .action-btn {{
            font-size: 0.95rem;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }}

        .btn-primary {{
            background: var(--accent-color);
            color: white;
        }}

        .btn-primary:hover {{
            background: var(--accent-hover);
        }}

        .btn-secondary {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-primary);
            border: 1px solid var(--card-border);
        }}

        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.1);
        }}

        footer.page-footer {{
            text-align: center;
            margin-top: 70px;
            padding-top: 30px;
            border-top: 1px solid var(--card-border);
            font-size: 0.95rem;
            color: var(--text-secondary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="date-badge">{thai_date}</div>
            <h1>Hacker News Daily Digest</h1>
            <p class="subtitle">สรุปข่าวยอดนิยมในรอบ 24 ชั่วโมงที่ผ่านมา แปลและสรุปผลการวิเคราะห์ในบอร์ดภาษาไทย</p>
        </header>

        <main class="news-list">
        """
        
    for i, s in enumerate(raw_stories, 1):
        s_id = s.get("id")
        title = s.get("title", "")
        url = s.get("url", "")
        hn_url = s.get("hn_url", "")
        points = s.get("points", 0)
        num_comments = s.get("num_comments", 0)
        
        domain = url.split("//")[-1].split("/")[0] if url else "news.ycombinator.com"
        if domain.startswith("www."):
            domain = domain[4:]
            
        story_summary = summaries.get(s_id, {})
        teaser = story_summary.get("teaser", title)
        article_summary = story_summary.get("article_summary", "")
        comments_summary = story_summary.get("comments_summary", "")
        
        if not article_summary:
            article_summary = f"<p>เนื้อหาบทความต้นฉบับ: {s.get('article_text', '')[:300]}...</p>"
        if not comments_summary:
            comments_summary = f"<p>สรุปความคิดเห็นเบื้องต้น: มีจำนวนความคิดเห็น {num_comments} รายการในกระทู้</p>"
            
        html_content += f"""
            <!-- STORY {i} -->
            <article class="news-item">
                <details>
                    <summary>
                        <div class="summary-header">
                            <div class="summary-title-section">
                                <h2 class="story-title">{title}</h2>
                                <p class="teaser">{teaser}</p>
                                <div class="meta-row">
                                    <span class="badge badge-points">🔥 {points} คะแนน</span>
                                    <span class="badge badge-comments">💬 {num_comments} ความคิดเห็น</span>
                                    <span class="badge badge-domain">{domain}</span>
                                </div>
                            </div>
                            <div class="toggle-icon">▼</div>
                        </div>
                    </summary>
                    <div class="details-content">
                        <section class="content-section">
                            <h3 class="section-header section-header-article">📄 สรุปเนื้อหาบทความ</h3>
                            <div class="section-body">
                                {article_summary}
                            </div>
                        </section>
                        <section class="content-section">
                            <h3 class="section-header section-header-discussion">💬 สรุปประเด็นเสวนาในกระทู้</h3>
                            <div class="section-body">
                                {comments_summary}
                            </div>
                        </section>
                        <div class="links-row">
                            <a href="{url}" target="_blank" class="action-btn btn-primary">อ่านบทความต้นฉบับ</a>
                            <a href="{hn_url}" target="_blank" class="action-btn btn-secondary">กระทู้บน Hacker News</a>
                        </div>
                    </div>
                </details>
            </article>
            """
            
    html_content += """
        </main>
        <footer class="page-footer">
            <p>Hacker News Daily Digest • จัดทำขึ้นโดยอัตโนมัติในทุกเช้าสำหรับคุณ</p>
            <p>ขนาดฟอนต์ถูกปรับแต่งให้อ่านง่ายเป็นพิเศษ (18px/1.75 Line Height)</p>
        </footer>
    </div>
</body>
</html>
    """
    
    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"สร้างไฟล์รายงาน '{html_filename}' สำเร็จเรียบร้อยแล้ว!")
    
    # 3. ประกอบหน้าปฏิทินสารบัญ index.html
    build_index_page(conn)
    conn.close()
    
    # 4. ทำความสะอาดไฟล์ JSON/Text ชั่วคราว
    print("กำลังทำความสะอาดไฟล์ชั่วคราว...")
    temp_files_to_remove = glob.glob("hn_summaries_*.json") + [
        "hn_summaries.json", "hn_temp_data.json", "stories_formatted.txt", "stories_formatted_utf8.txt"
    ]
    for file_path in temp_files_to_remove:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"ลบไฟล์ชั่วคราวสำเร็จ: {file_path}")
            except Exception as e:
                print(f"Warning: ไม่สามารถลบ {file_path} ได้: {e}")
                
    # 5. สั่งรัน Git Push ไปยัง GitHub Pages
    print("กำลังดำเนินระบบ Git Auto-Update ไปยัง GitHub...")
    try:
        subprocess.run(["git", "add", html_filename, "index.html"], check=True)
        commit_msg = f"Auto-update: Hacker News Digest for {latest_date}"
        
        status_res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status_res.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            subprocess.run(["git", "push"], check=True)
            print("พุชข้อมูลขึ้น GitHub Pages สำเร็จเรียบร้อยแล้ว!")
        else:
            print("ไม่มีข้อมูลเปลี่ยนแปลงเพิ่มเติมในระบบ Git")
    except Exception as e:
        print(f"Warning: การอัปเดตระบบ Git/GitHub อัตโนมัติล้มเหลว: {e}")

# =====================================================================
# 5. ฟังก์ชันเริ่มต้นรันโปรแกรมหลัก (Main Entrypoint)
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="Hacker News Daily Digest MVP Integrator")
    parser.add_argument("--fetch", action="store_true", help="รันเฉพาะเฟสดึงข้อมูลดิบลง SQLite")
    parser.add_argument("--build", action="store_true", help="รันเฉพาะเฟสประกอบเว็บ HTML และพุชขึ้น GitHub")
    args = parser.parse_args()
    
    # เลือกรันตาม Flags ที่ระบุ
    if args.fetch:
        run_fetch_phase()
    elif args.build:
        run_build_phase()
    else:
        # หากไม่มี flags เลย (รันเปล่าๆ) ให้รันแบบครบวงจร (สำหรับรัน Standalone)
        run_fetch_phase()
        run_ai_summarizer_phase()
        run_build_phase()

if __name__ == "__main__":
    main()
