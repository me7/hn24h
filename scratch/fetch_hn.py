# /// script
# dependencies = [
#   "requests",
#   "beautifulsoup4",
# ]
# ///

import os
import sys
import json
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

DB_NAME = "hn_knowledge_base.db"

def init_db():
    """
    สร้างฐานข้อมูลและตารางสำหรับเก็บข้อมูลข่าวสาร
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

# ป้องกันปัญหาแสดงผลภาษาไทยใน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def get_hn_stories(points_threshold=150, max_stories=40):
    """
    ดึงรายชื่อข่าวยอดนิยมจาก Hacker News ในรอบ 24 ชั่วโมงที่ผ่านมา (สูงสุด 40 ข่าว)
    """
    print("กำลังคำนวณเวลา 24 ชั่วโมงย้อนหลัง...")
    time_24h_ago = int((datetime.utcnow() - timedelta(hours=24)).timestamp())
    
    stories = []
    page = 0
    max_pages = 5  # เพิ่มเป็น 5 หน้าเพื่อเก็บข่าวให้ได้มากพอ
    
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
            
    # เรียงลำดับตามคะแนนสูงสุดลงมา
    stories.sort(key=lambda x: x["points"], reverse=True)
    
    # กรองเฉพาะกระทู้ที่มีคะแนนตามเกณฑ์ขั้นต่ำ
    filtered_stories = [s for s in stories if s["points"] >= points_threshold]
    
    # หากกรองแล้วมีข่าวน้อยกว่า 10 ข่าว ให้เอาตัวท็อปมาให้ครบอย่างน้อย 15 ข่าว (ถ้ามี)
    if len(filtered_stories) < 15 and len(stories) > 0:
        filtered_stories = stories[:max(15, len(stories))]
        
    # จำกัดจำนวนสูงสุดที่ 40 ข่าวตามต้องการ
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
    แปลงโครงสร้างความคิดเห็นที่ทับซ้อนกันให้เป็นข้อความแบนราบที่อ่านง่าย (ลดขนาดลงเหลือ 15 ความเห็นต่อข่าวเพื่อคุม Token)
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
        
        # แปลงข้อความคิดเห็น
        formatted_text, _ = format_comments(children, depth=0, max_comments=15)
        
        if len(formatted_text) > 5000:
            formatted_text = formatted_text[:5000] + "\n\n...[ความคิดเห็นเพิ่มเติมถูกละไว้]..."
            
        return formatted_text if formatted_text.strip() else "ไม่มีความคิดเห็นในกระทู้นี้"
    except Exception as e:
        return f"ไม่สามารถดึงข้อมูลความคิดเห็นได้: {str(e)}"

def main():
    try:
        # เตรียมระบบฐานข้อมูล
        init_db()
        
        # 1. ดึงข่าวยอดนิยม
        stories = get_hn_stories(points_threshold=150, max_stories=40)
        if not stories:
            print("ไม่พบข่าวเด่นที่มีคะแนนมากกว่า 150 ในช่วง 24 ชั่วโมงที่ผ่านมา")
            return
            
        # 2. ไล่ดึงเนื้อหาข่าวและคอมเมนต์ทีละข่าว
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for i, story in enumerate(stories, 1):
            print(f"\n--- กำลังประมวลผลข่าวที่ {i}/{len(stories)}: {story['title']} (คะแนน: {story['points']}) ---")
            
            if "item?id=" in story["url"]:
                article_text = "บทความนี้เป็นกระทู้พูดคุยบน Hacker News โดยตรง ไม่มีหน้าเว็บภายนอก"
            else:
                article_text = scrape_article_content(story["url"])
                
            comments_text = fetch_hn_comments(story["id"])
            
            # บันทึกลงฐานข้อมูล SQLite (ถ้ามีข้อมูลเดิมอยู่แล้วจะอัปเดตเฉพาะค่าดิบโดยรักษาสรุปเดิมไว้)
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
            
            # ป้องกันการยิงเว็บปลายทางถี่เกินไป
            time.sleep(0.5)
            
        conn.commit()
        conn.close()
        
        print(f"\nดึงข้อมูลเรียบร้อยและบันทึกลงฐานข้อมูล '{DB_NAME}' สำเร็จแล้ว! ทั้งหมด {len(stories)} ข่าว")
        
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงานหลัก: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
