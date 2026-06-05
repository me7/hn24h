# /// script
# dependencies = [
#   "google-generativeai",
# ]
# ///

import os
import sys
import sqlite3
import json
import google.generativeai as genai
from datetime import datetime

# กำหนดชื่อฐานข้อมูลและรุ่นโมเดล
DB_NAME = "hn_knowledge_base.db"
MODEL_NAME = "gemini-2.5-flash"  # ใช้โมดูลประสิทธิภาพสูงและประหยัดที่สุดสำหรับงานสรุป

def get_gemini_client():
    """
    ดึงสิทธิ์การใช้งาน Gemini API Key จาก Environment Variable
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: ไม่พบ GEMINI_API_KEY ใน Environment Variables ของระบบ")
        print("กรุณาตั้งค่าความปลอดภัยหรือระบุคีย์ก่อนรันสคริปต์นี้")
        return None
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)

def get_summaries_from_ai(model, title, article_text, comments_text):
    """
    ส่งข้อมูลข่าวสารไปสรุปเป็นภาษาไทยอย่างละเอียดผ่าน Gemini API
    """
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

def process_pending_summaries():
    """
    ดึงข่าวสารของวันนี้ที่ยังไม่มีบทสรุป มาสั่งงานสรุปผ่าน Gemini API
    """
    model = get_gemini_client()
    if not model:
        return False
        
    if not os.path.exists(DB_NAME):
        print(f"Error: ไม่พบไฟล์ฐานข้อมูล '{DB_NAME}'")
        return False
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # ค้นหาข่าวของวันนี้ที่บทสรุปยังเป็นค่าว่าง
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
    SELECT id, title, article_text, comments_text 
    FROM stories 
    WHERE fetched_date = ? AND (teaser IS NULL OR teaser = '' OR teaser = title);
    """, (today_str,))
    
    pending_stories = cursor.fetchall()
    if not pending_stories:
        print("ไม่พบข่าวสารที่ค้างการสรุปในวันนี้")
        conn.close()
        return True
        
    print(f"พบข่าวที่ต้องทำการสรุปทั้งหมด {len(pending_stories)} ข่าว กำลังทยอยรันสรุปผ่าน API...")
    
    success_count = 0
    for s_id, title, art_text, comm_text in pending_stories:
        print(f"-> กำลังส่งสรุปข่าว: {title}")
        
        # ส่งให้ AI คำนวณ
        ai_res = get_summaries_from_ai(model, title, art_text, comm_text)
        
        if ai_res:
            teaser = ai_res.get("teaser", title)
            art_sum = ai_res.get("article_summary", "")
            comm_sum = ai_res.get("comments_summary", "")
            
            # อัปเดตข้อมูลสรุปและแท็กจัดหมวดหมู่เบื้องต้นลงใน SQLite
            cursor.execute("""
            UPDATE stories SET
                teaser = ?,
                article_summary = ?,
                comments_summary = ?
            WHERE id = ?;
            """, (teaser, art_sum, comm_sum, s_id))
            
            # วิเคราะห์แท็กเบื้องต้นจากหัวข้อ (สามารถต่อยอดให้ AI สกัดแท็กได้)
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
            success_count += 1
        else:
            print(f"Warning: สรุปข่าว '{title}' ล้มเหลว ข้ามไปทำข่าวถัดไป")
            
    conn.close()
    print(f"เสร็จสิ้นภารกิจรันสรุปด้วย AI: ประมวลผลสำเร็จ {success_count}/{len(pending_stories)} ข่าว")
    return True

if __name__ == "__main__":
    print("เริ่มระบบประมวลผลสรุปข่าวอัจฉริยะแบบทำงานเป็นอิสระ (Standalone)")
    success = process_pending_summaries()
    if success:
        # ประกอบร่างไฟล์ HTML อัตโนมัติในขั้นตอนสุดท้าย
        print("\nกำลังเรียกประกอบร่างหน้าเว็บ HTML จากคลังข้อมูล SQLite...")
        os.system("python build_html.py")
