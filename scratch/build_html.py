import os
import json
import sys
import glob
from datetime import datetime

# ป้องกันปัญหาแสดงผลภาษาไทยใน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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

def main():
    try:
        # 1. โหลดและอัปเกรดบทสรุปภาษาไทยจากไฟล์ JSON (หากมีอยู่) ลงฐานข้อมูล SQLite
        db_name = "hn_knowledge_base.db"
        
        # ตรวจสอบโครงสร้างและนำเข้าบทสรุปถ้ามีไฟล์ JSON ค้างอยู่
        import sqlite3
        if os.path.exists(db_name):
            conn = sqlite3.connect(db_name)
            cursor = conn.cursor()
            
            json_summaries = {}
            # โหลดไฟล์หลัก
            if os.path.exists("hn_summaries.json"):
                try:
                    with open("hn_summaries.json", "r", encoding="utf-8") as f:
                        json_summaries.update(json.load(f))
                except Exception as e:
                    print(f"Warning: โหลดไฟล์หลัก hn_summaries.json ไม่สำเร็จ: {e}")
                    
            # โหลดไฟล์ย่อย
            for file_path in glob.glob("hn_summaries_*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        json_summaries.update(json.load(f))
                except Exception as e:
                    print(f"Warning: เกิดข้อผิดพลาดในการโหลดไฟล์ย่อย {file_path}: {e}")
                    
            if json_summaries:
                print(f"พบข้อมูลสรุปใหม่ในไฟล์ JSON ทั้งหมด {len(json_summaries)} ข่าว กำลังอัปเดตลงฐานข้อมูล...")
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

        # 2. โหลดข้อมูลข่าวดิบและบทสรุปจาก SQLite
        if not os.path.exists(db_name):
            print(f"Error: ไม่พบไฟล์ฐานข้อมูล '{db_name}'")
            return
            
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # ค้นหาวันที่ดึงข้อมูลล่าสุด
        cursor.execute("SELECT MAX(fetched_date) FROM stories;")
        latest_date = cursor.fetchone()[0]
        if not latest_date:
            print("Error: ไม่มีข้อมูลในฐานข้อมูล")
            conn.close()
            return
            
        print(f"กำลังดึงข้อมูลข่าวสารสำหรับวันที่ล่าสุดที่มีข้อมูล: {latest_date}")
        
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
                "id": s_id,
                "title": title,
                "url": url,
                "hn_url": hn_url,
                "points": points,
                "num_comments": num_comments,
                "author": author,
                "article_text": art_text,
                "comments_text": comm_text
            })
            summaries[s_id] = {
                "teaser": teaser if teaser else title,
                "article_summary": art_sum if art_sum else "",
                "comments_summary": comm_sum if comm_sum else ""
            }
            
        conn.close()
        print(f"โหลดข้อมูลสำเร็จทั้งหมด {len(raw_stories)} ข่าว")
            
        # 3. กำหนดชื่อไฟล์ HTML ตามวันปัจจุบัน
        today_str = datetime.now().strftime("%Y%m%d")
        html_filename = f"HN_{today_str}.html"
        thai_date = format_thai_date()
        
        # 4. ดีไซน์และโครงสร้าง HTML (ปรับปรุงขนาดฟอนต์ให้อ่านง่าย สบายตาสำหรับผู้สูงอายุ)
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
            font-size: 18px; /* เพิ่มขนาดฟอนต์หลักให้อ่านง่ายขึ้น ไม่ต้องซูม 125% */
            line-height: 1.75; /* เพิ่มความห่างระหว่างบรรทัด */
        }}

        .container {{
            max-width: 950px; /* ขยายขนาดการแสดงผลเล็กน้อย */
            margin: 0 auto;
            padding: 40px 20px;
        }}

        header {{
            text-align: center;
            margin-bottom: 50px;
        }}

        h1 {{
            font-family: var(--font-display);
            font-size: 2.8rem; /* ขยายขนาดหัวข้อใหญ่ */
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
            font-size: 1.05rem; /* ขยายฟอนต์ */
            color: var(--text-secondary);
            margin-bottom: 20px;
            font-weight: 600;
        }}

        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.25rem; /* ขยายฟอนต์คำอธิบาย */
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
            font-size: 1.45rem; /* ปรับเพิ่มขนาดหัวข้อข่าวให้อ่านง่าย */
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
            font-size: 1.15rem; /* ปรับเพิ่มขนาดสรุปสั้น */
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
            font-size: 0.85rem; /* ขยายขนาดป้าย */
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
            font-size: 1.25rem; /* ขยายขนาดหัวข้อย่อย */
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
            font-size: 1.08rem; /* ปรับขนาดฟอนต์รายละเอียด */
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
            font-size: 0.95rem; /* ขยายขนาดฟอนต์ปุ่มกด */
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
        
        # 5. วนลูปเพื่อประกอบข่าวย่อยลงใน HTML
        for i, s in enumerate(raw_stories, 1):
            story_id = s.get("id")
            title = s.get("title", "")
            url = s.get("url", "")
            hn_url = s.get("hn_url", "")
            points = s.get("points", 0)
            num_comments = s.get("num_comments", 0)
            
            # แยกชื่อโดเมน
            domain = url.split("//")[-1].split("/")[0] if url else "news.ycombinator.com"
            if domain.startswith("www."):
                domain = domain[4:]
                
            # ค้นหาบทสรุปภาษาไทยที่มีอยู่
            story_summary = summaries.get(story_id, {})
            teaser = story_summary.get("teaser", title)
            article_summary = story_summary.get("article_summary", "")
            comments_summary = story_summary.get("comments_summary", "")
            
            # หากไม่มีสรุปเชิงลึก ให้แสดงข้อความชี้แนะชั่วคราว
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
        
        # เขียนไฟล์ HTML ลงระบบ
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        print(f"สร้างไฟล์รายงาน '{html_filename}' สำเร็จเรียบร้อยแล้ว!")
        
        # 6. ทำความสะอาดไฟล์ชั่วคราวที่ไม่จำเป็นหลังจากสร้าง HTML สำเร็จ
        print("กำลังทำความสะอาดไฟล์ชั่วคราว...")
        
        # ลบไฟล์สรุปย่อย hn_summaries_*.json และไฟล์ชั่วคราวอื่นๆ ที่ดึงมาจัดสรรเข้าระบบแล้ว
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
                    
        print("เสร็จสิ้นการจัดเก็บและทำความสะอาดระบบ")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
