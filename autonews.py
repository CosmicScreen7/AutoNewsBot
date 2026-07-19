import os
import re
import datetime
import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"Failed to initialize Gemini AI: {e}")
        model = None
else:
    model = None

# Templates sequence to maintain the Grid
TEMPLATES = [
    "final_templates/template_single_1.html", # 0: Blue Gradient
    "final_templates/template_carousel.html", # 1: White Minimalist
    "final_templates/template_single_2.html"  # 2: Dark Glass Box
]

def get_next_template():
    state_file = "state.txt"
    idx = 0
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            try:
                idx = int(f.read().strip())
            except ValueError:
                idx = 0
                
    next_idx = (idx + 1) % len(TEMPLATES)
    with open(state_file, 'w') as f:
        f.write(str(next_idx))
        
    return TEMPLATES[idx]

def rewrite_with_ai(title, description):
    print("Rewriting content...")
    if not model:
        print("No Gemini API key found. Using default text.")
        return {"headline": title, "summary": description, "tag": "TECH NEWS"}
        
    try:
        prompt = f"""
        Act as an expert Instagram social media manager for a premium tech news agency 'INFIZY'.
        I have a raw news article. I need you to rewrite it for an Instagram post.
        Raw Title: {title}
        Raw Description: {description}
        
        Provide exactly 3 lines in this format, nothing else:
        HEADLINE: [Write a catchy headline, max 10 words]
        SUMMARY: [Write a highly engaging summary, max 3 lines/sentences]
        TAG: [A relevant 1-2 word tag like TECH NEWS, AI, STARTUPS, BREAKING]
        """
        response = model.generate_content(prompt)
        text = response.text
        
        headline = re.search(r"HEADLINE:\s*(.*)", text).group(1).strip()
        summary = re.search(r"SUMMARY:\s*(.*)", text).group(1).strip()
        tag = re.search(r"TAG:\s*(.*)", text).group(1).strip()
        
        # Clean quotes
        headline = headline.strip('"\'')
        
        print("AI Rewrite Successful!")
        return {"headline": headline, "summary": summary, "tag": tag}
    except Exception as e:
        print(f"AI Rewrite Failed: {e}. Falling back to default text.")
        return {"headline": title, "summary": description, "tag": "TECH NEWS"}

def get_latest_news():
    print("Fetching latest news from Google News RSS...")
    feed_url = "https://news.google.com/rss/search?q=technology+startups&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        print("No news found.")
        return None
        
    article = feed.entries[0]
    title = article.title
    link = article.link
    
    print(f"Top Article: {title}")
    print("Extracting article metadata...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        og_image = soup.find('meta', property='og:image')
        image_url = og_image['content'] if og_image else None
        
        og_desc = soup.find('meta', property='og:description')
        description = og_desc['content'] if og_desc else article.description
        
        if '<' in description or len(description) > 150:
            description = BeautifulSoup(description, 'html.parser').text
            if len(description) > 150:
                description = description[:147] + "..."
                
        if " - " in title:
            title = title.rsplit(" - ", 1)[0]
            
        return {
            "raw_title": title,
            "raw_summary": description,
            "image_url": image_url
        }
    except Exception as e:
        print(f"Error fetching article details: {e}")
        return None

def download_image(url, filename="background.jpg"):
    print(f"Downloading background image from {url}...")
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return os.path.abspath(filename)
    except Exception as e:
        print(f"Failed to download image: {e}")
    return None

def is_top_left_dark(image_path):
    print("Checking background brightness in the top-left corner...")
    try:
        img = Image.open(image_path).convert('L')
        width, height = img.size
        crop_box = (0, 0, min(200, width), min(200, height))
        cropped = img.crop(crop_box)
        stat = ImageStat.Stat(cropped)
        avg_brightness = stat.mean[0]
        print(f"Average brightness (0-255): {avg_brightness:.2f}")
        return avg_brightness < 120
    except Exception as e:
        print(f"Error analyzing image: {e}")
        return False

def render_html_to_image(html_path, output_path):
    print(f"Rendering HTML to {output_path}...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2, viewport={"width": 1080, "height": 1350})
        page.goto(f"file:///{os.path.abspath(html_path)}")
        page.wait_for_timeout(2000)
        page.screenshot(path=output_path, type='jpeg', quality=95)
        browser.close()

def main():
    # Setup Output Directory
    os.makedirs("output", exist_ok=True)

    news_data = get_latest_news()
    if not news_data or not news_data['image_url']:
        print("Failed to get suitable news data. Exiting.")
        return
        
    bg_path = download_image(news_data['image_url'])
    if not bg_path:
        print("Failed to get background image. Exiting.")
        return
        
    # AI Rewrite
    ai_content = rewrite_with_ai(news_data['raw_title'], news_data['raw_summary'])
    
    is_dark = is_top_left_dark(bg_path)
    print(f"Top-left corner is dark: {is_dark}")
    
    # Pick next template in cycle
    template_path = get_next_template()
    print(f"Using template: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        
    # Inject Data
    title_el = soup.find(id="title-text")
    if title_el: title_el.string = ai_content['headline']
    
    summary_el = soup.find(id="summary-text")
    if summary_el: summary_el.string = ai_content['summary']
    
    tag_el = soup.find(id="tag-text")
    if tag_el: tag_el.string = ai_content['tag']
    
    # Background Image
    bg_layer = soup.find(id="bg-layer")
    if bg_layer:
        file_uri = f"file:///{bg_path.replace(chr(92), '/')}" 
        bg_layer['style'] = f"background-image: url('{file_uri}') !important;"
        
    # Smart Color Inversion
    if is_dark:
        print("Applying Smart Color Inversion (White Logo)...")
        style_tag = soup.new_tag("style")
        style_tag.string = ".logo-img { filter: brightness(0) invert(1) drop-shadow(0 2px 10px rgba(0,0,0,0.5)) !important; }"
        soup.head.append(style_tag)

    out_html = "final_templates/generated_post.html"
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(str(soup))
        
    # Generate timestamped output filename
    safe_title = "".join([c for c in ai_content['headline'] if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    safe_title = safe_title.replace(" ", "_")[:30]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    final_output_path = f"output/{timestamp}_{safe_title}.jpg"
    
    render_html_to_image(out_html, final_output_path)
    print(f"Done! Post successfully saved to: {final_output_path}")

if __name__ == "__main__":
    main()
