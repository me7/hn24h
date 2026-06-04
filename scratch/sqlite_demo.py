import sqlite3
import json
import os
from datetime import datetime

# กำหนดชื่อฐานข้อมูล
DB_NAME = "hn_knowledge_base.db"

def init_db():
    """
    สร้างฐานข้อมูลและตารางที่จำเป็นสำหรับคลังความรู้ส่วนตัว
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # เปิดการใช้งาน Foreign Key Constraints
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. ตารางเก็บข้อมูลข่าวสารและบทสรุปภาษาไทย
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT,
        hn_url TEXT,
        points INTEGER,
        num_comments INTEGER,
        teaser TEXT,
        article_summary TEXT,
        comments_summary TEXT,
        fetched_date TEXT NOT NULL
    );
    """)
    
    # 2. ตารางเก็บรายชื่อแท็ก (หมวดหมู่ความรู้)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    """)
    
    # 3. ตารางเชื่อมโยงความสัมพันธ์ข่าวกับแท็ก (Many-to-Many)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_tags (
        story_id TEXT,
        tag_id INTEGER,
        PRIMARY KEY (story_id, tag_id),
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
    );
    """)
    
    # 4. สร้างตาราง Virtual Table สำหรับช่วยค้นหาคำแบบรวดเร็ว (SQLite Full-Text Search FTS5)
    # ช่วยให้เราสามารถพิมพ์ค้นหาคำในเนื้อหาบทสรุปภาษาไทยหรือหัวข้อข่าวได้ทันที
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS stories_fts USING fts5(
        id UNINDEXED,
        title,
        teaser,
        article_summary,
        comments_summary
    );
    """)
    
    conn.commit()
    conn.close()
    print(f"สร้างฐานข้อมูล '{DB_NAME}' และตารางพร้อมทำดัชนีสืบค้นคำ (FTS5) เรียบร้อยแล้ว!")

def insert_story(story_data, tags_list=None):
    """
    บันทึกหรืออัปเดตข้อมูลข่าวสารพร้อมระบบติดแท็กจัดหมวดหมู่
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    story_id = story_data["id"]
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # บันทึกหรือเขียนทับข้อมูลข่าวสาร
    cursor.execute("""
    INSERT OR REPLACE INTO stories (
        id, title, url, hn_url, points, num_comments, teaser, article_summary, comments_summary, fetched_date
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        story_id,
        story_data.get("title", ""),
        story_data.get("url", ""),
        story_data.get("hn_url", ""),
        story_data.get("points", 0),
        story_data.get("num_comments", 0),
        story_data.get("teaser", ""),
        story_data.get("article_summary", ""),
        story_data.get("comments_summary", ""),
        today_str
    ))
    
    # ปรับปรุงข้อมูลในตารางสืบค้นด่วน (FTS)
    cursor.execute("DELETE FROM stories_fts WHERE id = ?;", (story_id,))
    cursor.execute("""
    INSERT INTO stories_fts (id, title, teaser, article_summary, comments_summary)
    VALUES (?, ?, ?, ?, ?);
    """, (
        story_id,
        story_data.get("title", ""),
        story_data.get("teaser", ""),
        story_data.get("article_summary", ""),
        story_data.get("comments_summary", "")
    ))
    
    # จัดการส่วนของแท็กจัดหมวดหมู่
    if tags_list:
        for tag_name in tags_list:
            tag_name = tag_name.strip().lower()
            if not tag_name:
                continue
                
            # บันทึกแท็กหากยังไม่มี
            cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?);", (tag_name,))
            
            # ดึง ID ของแท็กนั้นๆ
            cursor.execute("SELECT id FROM tags WHERE name = ?;", (tag_name,))
            tag_id = cursor.fetchone()[0]
            
            # เชื่อมโยงข่าวเข้ากับแท็ก
            cursor.execute("INSERT OR IGNORE INTO story_tags (story_id, tag_id) VALUES (?, ?);", (story_id, tag_id))
            
    conn.commit()
    conn.close()
    print(f"บันทึกข่าว ID: {story_id} และแท็ก {tags_list} สำเร็จ")

def query_stories_by_tag(tag_name):
    """
    คิวรี่กรองข้อมูลข่าวตามแท็กเฉพาะเจาะจง
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.id, s.title, s.teaser, s.fetched_date 
    FROM stories s
    JOIN story_tags st ON s.id = st.story_id
    JOIN tags t ON st.tag_id = t.id
    WHERE t.name = ?
    ORDER BY s.fetched_date DESC;
    """, (tag_name.lower(),))
    
    results = cursor.fetchall()
    conn.close()
    return results

def full_text_search(search_query):
    """
    ค้นหาข้อมูลข่าวอย่างรวดเร็วจากคำค้นหา (ตัวช่วย FTS5)
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.id, s.title, s.teaser, s.fetched_date 
    FROM stories s
    JOIN stories_fts f ON s.id = f.id
    WHERE stories_fts MATCH ?
    ORDER BY rank;
    """, (search_query,))
    
    results = cursor.fetchall()
    conn.close()
    return results

# ส่วนการทดสอบสาธิตระบบ
if __name__ == "__main__":
    init_db()
    
    # จำลองข้อมูลเพื่อบันทึก
    demo_story = {
        "id": "48386725",
        "title": "Gooey: A GPU-accelerated UI framework for Zig",
        "url": "https://github.com/duanebester/gooey",
        "hn_url": "https://news.ycombinator.com/item?id=48386725",
        "points": 159,
        "num_comments": 58,
        "teaser": "Gooey เป็น GUI framework สำหรับ Zig ที่มีความคุ้มค่า เรนเดอร์ด้วย GPU และไม่มี Dependencies ภายนอก",
        "article_summary": "<p>Gooey เขียนขึ้นมาด้วยภาษา Zig ล้วนๆ เรนเดอร์ผ่าน Vulkan และ Metal...</p>",
        "comments_summary": "<p>ดราม่าในบอร์ดเกี่ยวกับประเด็นการใช้ Claude Code และเรื่องคุณภาพโค้ด...</p>"
    }
    
    # ลองทำการบันทึกพร้อมแปะแท็ก
    insert_story(demo_story, tags_list=["zig", "ui", "ai-code"])
    
    # 1. ทดสอบการค้นหาโดยใช้แท็ก
    print("\n--- ค้นหาข่าวที่มีแท็ก 'zig' ---")
    stories_zig = query_stories_by_tag("zig")
    for s in stories_zig:
        print(f"[{s[3]}] ID: {s[0]} | Title: {s[1]}\nSummary: {s[2]}\n")
        
    # 2. ทดสอบระบบเสิร์ช Full-Text Search (ค้นหาคำว่า "ดราม่า")
    print("--- ค้นหาคำว่า 'ดราม่า' ในคลังข่าว ---")
    search_results = full_text_search("ดราม่า")
    for s in search_results:
        print(f"[{s[3]}] ID: {s[0]} | Title: {s[1]}\nSummary: {s[2]}\n")
