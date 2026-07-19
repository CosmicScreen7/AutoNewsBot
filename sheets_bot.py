import os
import re
import datetime
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import urllib.parse

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load Environment Variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "AutoNewsBot_Database")

# Email Config
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
if not EMAIL_RECEIVER and EMAIL_SENDER:
    EMAIL_RECEIVER = EMAIL_SENDER

# Try initializing Gemini
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-3.5-flash')
    except Exception as e:
        print(f"Failed to initialize Gemini: {e}")
        model = None
else:
    print("GEMINI_API_KEY is missing or empty!")
    model = None

def get_google_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_path = "credentials.json"
    
    if "GOOGLE_CREDENTIALS_JSON" in os.environ:
        with open(creds_path, "w") as f:
            f.write(os.environ["GOOGLE_CREDENTIALS_JSON"])
            
    if not os.path.exists(creds_path):
        print("\n[ERROR] 'credentials.json' not found!")
        return None
        
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"[ERROR] Auth failed: {e}")
        return None

def setup_sheets(client):
    try:
        doc = client.open(SPREADSHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"[ERROR] Spreadsheet '{SPREADSHEET_NAME}' not found.")
        return None, None, None

    try: ws_planning = doc.worksheet("Planning")
    except: ws_planning = doc.add_worksheet(title="Planning", rows="100", cols="14")
    
    try: ws_posted = doc.worksheet("Posted")
    except: ws_posted = doc.add_worksheet(title="Posted", rows="100", cols="14")
    
    try: ws_memory = doc.worksheet("MemoryBank")
    except: ws_memory = doc.add_worksheet(title="MemoryBank", rows="100", cols="5")

    plan_headers = ["Date Added", "Topic", "AI Headline", "GitHub Image 1", "GitHub Image 2", "GitHub Image 3", "GitHub Image 4", "GitHub Image 5", "Insta Caption", "Hashtags", "Auto-Post Time", "Status"]
    if not ws_planning.row_values(1): ws_planning.append_row(plan_headers)
    if not ws_posted.row_values(1): ws_posted.append_row(plan_headers)
    
    mem_headers = ["Date Posted", "Topic", "Headline Used"]
    if not ws_memory.row_values(1): ws_memory.append_row(mem_headers)

    return ws_planning, ws_posted, ws_memory

def send_email(subject, body):
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD:
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

def fetch_news_to_sheet(ws_planning, ws_memory):
    print("Fetching trending news from multiple Google News RSS feeds...")
    feeds = [
        "https://news.google.com/rss/search?q=technology+startups&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=artificial+intelligence+trending&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=tech+gadgets+launch&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=cybersecurity+news&hl=en-US&gl=US&ceid=US:en"
    ]
    
    all_articles = []
    for feed_url in feeds:
        parsed_feed = feedparser.parse(feed_url)
        all_articles.extend(parsed_feed.entries[:5])
    
    random.shuffle(all_articles)
    
    existing_plan = ws_planning.col_values(2)
    existing_mem = ws_memory.col_values(2)
    all_existing = existing_plan + existing_mem
    
    added_count = 0
    for article in all_articles:
        if added_count >= 1: break
        
        title = article.title.rsplit(" - ", 1)[0] if " - " in article.title else article.title
        if title in all_existing: continue
            
        date_str = datetime.datetime.now().strftime("%d-%b-%Y %H:%M")
        ws_planning.append_row([date_str, title, "", "", "", "", "", "", "", "", "", "NEW"])
        print(f"Added NEW trending topic: {title}")
        added_count += 1

def parse_ai_response(res):
    try:
        f = re.search(r"FORMAT:\s*(.*)", res, re.IGNORECASE).group(1).strip().upper()
    except:
        f = "SINGLE"

    try:
        h = re.search(r"HEADLINE:\s*(.*)", res).group(1).strip().strip('"\'')
    except: h = "Breaking Tech News"
    
    try:
        c = re.search(r"CAPTION:\s*(.*)", res).group(1).strip()
    except: c = "Check out the latest update! 🚀"
    
    try:
        t = re.search(r"HASHTAGS:\s*(.*)", res).group(1).strip()
    except: t = "#Tech #News"
    
    try:
        tag = re.search(r"TAG:\s*(.*)", res).group(1).strip().upper()
    except: tag = "TECH NEWS"
    
    try:
        img_prompt = re.search(r"IMAGE_PROMPT:\s*(.*)", res).group(1).strip()
    except: img_prompt = "A high tech futuristic abstract background with dark blue and purple neon lights"
    
    summaries = []
    for i in range(1, 5):
        match = re.search(f"SUMMARY_{i}:\s*(.*)", res)
        if match and match.group(1).strip():
            summaries.append(match.group(1).strip())
            
    if not summaries:
        summaries = ["Read the full story in the caption below!"]
        
    return {"format": f, "headline": h, "summaries": summaries, "caption": c, "hashtags": t, "tag": tag, "image_prompt": img_prompt}

def process_new_rows(ws_planning, ws_memory):
    rows = ws_planning.get_all_values()
    os.makedirs("output", exist_ok=True)
    
    memory_history = ws_memory.get_all_values()
    history_text = "\\n".join([f"Past Topic: {r[1]} | Headline Used: {r[2]}" for r in memory_history[1:10]]) if len(memory_history) > 1 else "No past history."
    
    for i, row in enumerate(rows):
        if i == 0: continue
        if len(row) > 11 and row[11] == "NEW":
            topic = row[1]
            print(f"Processing Row {i+1}: {topic}")
            
            if model:
                prompt = f"""
                Act as an expert Instagram manager for 'INFIZY'. Topic: {topic}
                
                ANTI-DUPLICATION RULE: Ensure this new post does NOT sound like past headlines.
                History: {history_text}
                
                STEP 1: Decide the FORMAT. 
                If the news is deep and requires explanation, choose CAROUSEL. If it's a quick update, choose SINGLE.
                
                STEP 2: Write the content based on strict MIN/MAX word limits.
                If CAROUSEL:
                - HEADLINE: Min 4, Max 10 words.
                - SUMMARY_X: Provide 2 to 4 summary points. Each point MUST be Min 10, Max 15 words.
                
                If SINGLE:
                - HEADLINE: Min 5, Max 12 words.
                - SUMMARY_1: Provide exactly ONE summary point. It MUST be Min 15, Max 30 words.
                
                Provide exactly this output structure:
                FORMAT: [SINGLE or CAROUSEL]
                HEADLINE: [Your Headline]
                SUMMARY_1: [Point 1]
                SUMMARY_2: [Point 2. Leave blank if SINGLE or not needed]
                SUMMARY_3: [Point 3. Leave blank if not needed]
                SUMMARY_4: [Point 4. Leave blank if not needed]
                CAPTION: [Instagram caption with emojis, max 3 sentences]
                HASHTAGS: [5 relevant hashtags]
                TAG: [1-2 word category, e.g., AI, STARTUP, BREAKING]
                IMAGE_PROMPT: [A highly detailed, hyper-realistic, dark-themed image prompt representing the news visually. Do NOT include any text in the image prompt.]
                """
                try:
                    res = model.generate_content(prompt).text
                    ai_data = parse_ai_response(res)
                except Exception as e:
                    print(f"AI Parse Error: {e}")
                    ai_data = {"format": "SINGLE", "headline": topic[:50], "summaries": ["Read more below!"], "caption": "Check out this news! 🚀", "hashtags": "#Tech #News", "tag": "NEWS"}
            else:
                print("Skipping AI Generation because model is None")
                ai_data = {"format": "SINGLE", "headline": topic[:50], "summaries": ["Read more below!"], "caption": "Check out this news! 🚀", "hashtags": "#Tech #News", "tag": "NEWS", "image_prompt": "A futuristic technology background"}
            
            encoded_prompt = urllib.parse.quote(ai_data['image_prompt'])
            bg_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1350&nologo=true"
            r = requests.get(bg_url, stream=True)
            bg_path = os.path.abspath("background.jpg")
            with open(bg_path, 'wb') as f:
                for chunk in r.iter_content(1024): f.write(chunk)
                
            img = Image.open(bg_path).convert('L')
            is_dark = ImageStat.Stat(img.crop((0,0,200,200))).mean[0] < 120
            
            safe_title = "".join([c for c in ai_data['headline'] if c.isalnum()]).replace(" ", "_")[:20]
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            generated_images = []
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                
                if ai_data['format'] == "CAROUSEL":
                    template_path = "final_templates/template_carousel.html"
                    with open(template_path, 'r', encoding='utf-8') as f: html_content = f.read()
                    
                    total_slides = 1 + len(ai_data['summaries'])
                    slides = [{"body_class": "slide-type-1", "seq": f"1/{total_slides}", "title": ai_data['headline'], "summary": ""}]
                    
                    for idx, summary in enumerate(ai_data['summaries']):
                        is_last = (idx == len(ai_data['summaries']) - 1)
                        slides.append({
                            "body_class": "slide-type-n last-slide" if is_last else "slide-type-n",
                            "seq": f"{idx+2}/{total_slides}",
                            "title": "",
                            "summary": summary + ("\\n\\nRead Caption ↓" if is_last else "")
                        })
                    
                    for slide_idx, slide_data in enumerate(slides):
                        soup = BeautifulSoup(html_content, 'html.parser')
                        if soup.body and slide_data["body_class"]: soup.body['class'] = slide_data["body_class"]
                        if soup.find(id="sequence-text"): soup.find(id="sequence-text").string = slide_data["seq"]
                        
                        if slide_idx == 0:
                            if soup.find(id="title-text"): soup.find(id="title-text").string = slide_data["title"]
                        else:
                            if soup.find(id="summary-text"): soup.find(id="summary-text").string = slide_data["summary"]
                            
                        if soup.find(id="tag-text"): soup.find(id="tag-text").string = ai_data['tag']
                        
                        bg_layer = soup.find(id="bg-layer")
                        if bg_layer: bg_layer['style'] = f"background-image: url('file:///{bg_path.replace(chr(92), '/')}') !important;"
                        
                        if is_dark:
                            style_tag = soup.new_tag("style")
                            style_tag.string = ".logo-img { filter: brightness(0) invert(1) drop-shadow(0 2px 10px rgba(0,0,0,0.5)) !important; }"
                            if soup.head: soup.head.append(style_tag)
                            
                        out_html = f"final_templates/generated_post_slide_{slide_idx}.html"
                        with open(out_html, 'w', encoding='utf-8') as f: f.write(str(soup))
                        
                        final_img = f"output/{timestamp}_{safe_title}_{slide_idx+1}.jpg"
                        page = browser.new_page(device_scale_factor=2, viewport={"width": 1080, "height": 1350})
                        page.goto(f"file:///{os.path.abspath(out_html)}")
                        page.wait_for_timeout(1000)
                        page.screenshot(path=final_img, type='jpeg', quality=95)
                        raw_url = f"https://raw.githubusercontent.com/CosmicScreen7/AutoNewsBot/main/{final_img}"
                        generated_images.append(raw_url)
                        page.close()
                else: # SINGLE
                    # Pick random single template
                    template_path = random.choice(["final_templates/template_single_1.html", "final_templates/template_single_2.html"])
                    with open(template_path, 'r', encoding='utf-8') as f: html_content = f.read()
                    
                    soup = BeautifulSoup(html_content, 'html.parser')
                    if soup.find(id="title-text"): soup.find(id="title-text").string = ai_data['headline']
                    
                    # Combine summaries into one for single post
                    comb_sum = " ".join(ai_data['summaries'])
                    if soup.find(id="summary-text"): soup.find(id="summary-text").string = comb_sum
                    if soup.find(id="tag-text"): soup.find(id="tag-text").string = ai_data['tag']
                    
                    bg_layer = soup.find(id="bg-layer")
                    if bg_layer: bg_layer['style'] = f"background-image: url('file:///{bg_path.replace(chr(92), '/')}') !important;"
                    
                    if is_dark:
                        style_tag = soup.new_tag("style")
                        style_tag.string = ".logo-img { filter: brightness(0) invert(1) drop-shadow(0 2px 10px rgba(0,0,0,0.5)) !important; }"
                        if soup.head: soup.head.append(style_tag)
                        
                    out_html = "final_templates/generated_post.html"
                    with open(out_html, 'w', encoding='utf-8') as f: f.write(str(soup))
                    
                    final_img = f"output/{timestamp}_{safe_title}.jpg"
                    page = browser.new_page(device_scale_factor=2, viewport={"width": 1080, "height": 1350})
                    page.goto(f"file:///{os.path.abspath(out_html)}")
                    page.wait_for_timeout(2000)
                    page.screenshot(path=final_img, type='jpeg', quality=95)
                    raw_url = f"https://raw.githubusercontent.com/CosmicScreen7/AutoNewsBot/main/{final_img}"
                    generated_images.append(raw_url)
                    page.close()
                
                browser.close()
            
            # Make.com will read this row
            ws_planning.update_cell(i+1, 3, ai_data['headline'])
            for j in range(5):
                ws_planning.update_cell(i+1, 4+j, generated_images[j] if j < len(generated_images) else "")
                
            ws_planning.update_cell(i+1, 9, ai_data['caption'])
            ws_planning.update_cell(i+1, 10, ai_data['hashtags'])
            
            post_time = (datetime.datetime.now() + datetime.timedelta(hours=1)).strftime("%I:%M %p")
            ws_planning.update_cell(i+1, 11, post_time)
            
            ws_planning.update_cell(i+1, 12, "READY_TO_POST")
            
            ws_memory.append_row([timestamp, topic, ai_data['headline']])
            send_email("✅ INFIZY Post Ready!", f"Generated '{topic}' in {ai_data['format']} format.\\nStatus updated to READY_TO_POST.")

def clean_old_images(ws_planning):
    rows = ws_planning.get_all_values()[1:]
    active_images = []
    for r in rows:
        if r[11] in ["NEW", "READY_TO_POST"]:
            active_images.extend(r[3:8])
            
    active_images = [os.path.basename(p) for p in active_images if p]
    
    out_dir = "output"
    if os.path.exists(out_dir):
        for f in os.listdir(out_dir):
            if f.endswith(".jpg") and f not in active_images:
                try: os.remove(os.path.join(out_dir, f))
                except: pass

def main():
    print("--- AutoNewsBot Started ---")
    client = get_google_client()
    if not client: return
    
    ws_planning, ws_posted, ws_memory = setup_sheets(client)
    if not ws_planning: return
    
    clean_old_images(ws_planning)
    
    print("\\n[1] Fetching Trending Topics...")
    fetch_news_to_sheet(ws_planning, ws_memory)
    
    print("\\n[2] Processing Content...")
    process_new_rows(ws_planning, ws_memory)
    
    print("\\n--- Complete ---")

if __name__ == "__main__":
    main()
