import json
import sys

# ป้องกันปัญหาแสดงผลภาษาไทยใน Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    try:
        with open("hn_temp_data.json", "r", encoding="utf-8") as f:
            stories = json.load(f)
            
        with open("stories_formatted_utf8.txt", "w", encoding="utf-8") as out:
            out.write(f"พบข่าวทั้งหมด: {len(stories)} ข่าว\n\n")
            
            for i, s in enumerate(stories, 1):
                out.write(f"=== STORY {i} ===\n")
                out.write(f"ID: {s.get('id')}\n")
                out.write(f"Title: {s.get('title')}\n")
                out.write(f"Points: {s.get('points')}\n")
                out.write(f"Comments Count: {s.get('num_comments')}\n")
                out.write(f"URL: {s.get('url')}\n")
                out.write(f"HN URL: {s.get('hn_url')}\n\n")
                
                # ย่อบทความ
                art_text = s.get('article_text', '')
                if len(art_text) > 3000:
                    art_text = art_text[:3000] + "\n...[เนื้อหาบทความถูกย่อเพื่อให้เอเจนต์ประมวลผลได้ดีขึ้น]..."
                out.write(f"Article Text:\n{art_text}\n\n")
                
                # ย่อคอมเมนต์
                comm_text = s.get('comments_text', '')
                if len(comm_text) > 2000:
                    comm_text = comm_text[:2000] + "\n...[ความคิดเห็นถูกย่อเพื่อให้เอเจนต์ประมวลผลได้ดีขึ้น]..."
                out.write(f"Comments Text:\n{comm_text}\n")
                out.write("=" * 60 + "\n\n")
            
        print("เขียนไฟล์ 'stories_formatted_utf8.txt' สำเร็จแล้ว!")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
