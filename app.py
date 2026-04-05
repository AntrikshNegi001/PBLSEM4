import os
import shutil
import time
import re
from flask import Flask, render_template, request
from bs4 import BeautifulSoup
from google import genai
import undetected_chromedriver as uc
import json # MAKE SURE THIS IS AT THE TOP OF YOUR FILE
app = Flask(__name__)

# --- CLEANUP ---
driver_cache = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
if os.path.exists(driver_cache):
    try: shutil.rmtree(driver_cache, ignore_errors=True)
    except: pass

# --- CONFIGURATION ---
client = genai.Client(api_key="AIzaSyCl8OQ1C9TridCO4lKPDGi3kAhJN9xl8p8")
MODEL_ID = 'gemini-2.5-flash'

def get_stealth_driver():
    options = uc.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.page_load_strategy = 'normal' 
    
    # ADVANCED SPOOFING: Hide the automation flag and fake a standard Windows user agent
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    driver = uc.Chrome(options=options, use_subprocess=True, version_main=146)
    driver.set_page_load_timeout(20) 
    return driver

# --- FILTER LOGIC ---
# --- FILTER LOGIC ---
def is_relevant(query, title):
    if not title or title in ["Title Unknown", "Not Found", "Error", "Blocked by Bot Check", "Product Not Found"]:
        return False

    clean_query = query.lower().replace(" ", "").replace("-", "")
    clean_title = title.lower().replace(" ", "").replace("-", "")
    
    if clean_query in clean_title: return True
        
    query_words = [w for w in query.lower().split() if len(w) > 1]
    title_lower = title.lower()
    
    # 1. CRITICAL NUMBER CHECK: If you search "iPhone 15", it MUST find "15"
    numbers_in_query = [w for w in query_words if any(char.isdigit() for char in w)]
    for num in numbers_in_query:
        if not re.search(rf'\b{num}\b', title_lower.replace("-", " ")):
            return False # Immediately block if the specific number/model is missing
            
    # 2. RELAXED WORD MATCH: Require only 60% of the words to match
    match_count = sum(1 for word in query_words if word in title_lower)
    return match_count >= (len(query_words) * 0.6)

# --- EXTRACTION LOGIC (Reads HTML only, no browsers here) ---
def extract_amazon(html, query):
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', {'data-component-type': 's-search-result'})
    if not items: 
        return {"site": "Amazon", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}
    
    target_item = items[0]
    for item in items:
        if not item.find(string=re.compile(r'Sponsored', re.IGNORECASE)):
            target_item = item
            break

    title_el = target_item.select_one('h2 span, span.a-text-normal')
    title = title_el.text.strip() if title_el else "Title Unknown"
    
    if title in ["Title Unknown", "Not Found", "Error"]:
        return {"site": "Amazon", "title": "Blocked by Bot Check", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Blocked", "link": "#"}

    if not is_relevant(query, title):
        return {"site": "Amazon", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}

    price_el = target_item.select_one('span.a-price-whole')
    price = f"₹{price_el.text.strip()}" if price_el else "Price Unknown"
    review_el = target_item.select_one('span.a-icon-alt')
    reviews = review_el.text.strip().split(' ')[0] if review_el else "No Ratings"

    a_tag = target_item.find('a', href=re.compile(r'/dp/|/gp/'))
    link = "https://www.amazon.in" + a_tag['href'] if a_tag and 'href' in a_tag.attrs else "#"
    img_tag = target_item.select_one('img.s-image')
    image = img_tag['src'] if img_tag else "https://placehold.co/200x200/eeeeee/999999?text=No+Image"
    return {"site": "Amazon", "title": title, "price": price, "reviews": reviews, "image": image, "link": link}

def extract_flipkart(html, query):
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', attrs={'data-id': True})
    if not items: 
        return {"site": "Flipkart", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}

    target_item = items[0]
    for item in items:
        if not item.find(string=re.compile(r'^Ad$', re.IGNORECASE)):
            target_item = item
            break

    title_el = target_item.select_one('a[title], a.WkTcLC, a.IRpwTa, div.KzDlHZ')
    title = title_el['title'] if title_el and 'title' in title_el.attrs else (title_el.text.strip() if title_el else "Title Unknown")

    if title in ["Title Unknown", "Not Found", "Error"]:
        return {"site": "Flipkart", "title": "Blocked by Bot Check", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Blocked", "link": "#"}

    if not is_relevant(query, title):
        return {"site": "Flipkart", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}

    price_el = target_item.select_one('div.Nx9bqj, div._30jeq3')
    if not price_el: price_el = target_item.find(string=re.compile(r'^₹[0-9,]+$'))
    price = price_el.text.strip() if hasattr(price_el, 'text') else (str(price_el).strip() if price_el else "Price Unknown")

    review_el = target_item.find('div', string=re.compile(r'^\d\.\d$'))
    reviews = review_el.text.strip() if review_el else "No Ratings"

    a_tag = target_item.select_one('a')
    raw_link = a_tag['href'] if a_tag and 'href' in a_tag.attrs else "#"
    link = raw_link if raw_link.startswith('http') else "https://www.flipkart.com" + raw_link if raw_link != "#" else "#"
    img_tag = target_item.select_one('img')
    image = img_tag['src'] if img_tag and 'src' in img_tag.attrs else "https://placehold.co/200x200/eeeeee/999999?text=No+Image"
    return {"site": "Flipkart", "title": title, "price": price, "reviews": reviews, "image": image, "link": link}

def extract_nykaa(html, query):
    soup = BeautifulSoup(html, 'html.parser')
    item_links = soup.find_all('a', href=re.compile(r'/p/'))
    if not item_links: 
        return {"site": "Nykaa", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}

    target_card, target_link = None, item_links[0]
    for item_link in item_links:
        card = item_link.find_parent('div', class_=re.compile(r'css-.*')) or item_link.parent
        if card.find(string=re.compile(r'₹')):
            target_card, target_link = card, item_link
            break

    if not target_card: 
        return {"site": "Nykaa", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}

    img_tag = target_card.find('img')
    title_el = target_card.find('h2') or target_card.find('div', class_=re.compile(r'title|name|xrzm88'))
    title = title_el.text.strip() if title_el and title_el.text.strip() else (img_tag['alt'] if img_tag and 'alt' in img_tag.attrs else "Title Unknown")

    if title in ["Title Unknown", "Not Found", "Error"]:
        return {"site": "Nykaa", "title": "Blocked by Bot Check", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Blocked", "link": "#"}

    if not is_relevant(query, title):
        return {"site": "Nykaa", "title": "Item not on website", "price": "N/A", "reviews": "N/A", "image": "https://placehold.co/200x200/eeeeee/999999?text=Not+Found", "link": "#"}

    price_el = target_card.find(string=re.compile(r'₹'))
    price = price_el.strip() if price_el else "Price Unknown"
    review_el = target_card.find('span', string=re.compile(r'\(\d+\)'))
    reviews = review_el.text.strip() if review_el else "No Ratings"

    raw_link = target_link['href']
    link = raw_link if raw_link.startswith('http') else "https://www.nykaa.com" + raw_link
    image = img_tag['src'] if img_tag and 'src' in img_tag.attrs else "https://placehold.co/200x200/eeeeee/999999?text=No+Image"
    return {"site": "Nykaa", "title": title, "price": price, "reviews": reviews, "image": image, "link": link}

# --- DIRECT LINK PARSER (The Source of Truth) ---
# --- DIRECT LINK PARSER ---
def scrape_direct_product(url):
    driver = None
    try:
        print("Scraping direct product link...")
        driver = get_stealth_driver()
        driver.get(url)
        time.sleep(4) 
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        site = "Amazon" if "amazon" in url else "Flipkart" if "flipkart" in url else "Nykaa" if "nykaa" in url else "Web"
        
        # 1. Try the standard Meta Tags first
        title_meta = soup.find('meta', property=re.compile(r'og:title', re.IGNORECASE))
        img_meta = soup.find('meta', property=re.compile(r'og:image', re.IGNORECASE))
        
        raw_title = title_meta['content'] if title_meta and 'content' in title_meta.attrs else driver.title
        image = img_meta['content'] if img_meta and 'content' in img_meta.attrs else None
        
        # 2. AMAZON FALLBACK: If Meta Tags are blocked, hunt the specific Amazon HTML ID
        if not image:
            amz_img = soup.find('img', id='landingImage') or soup.find('img', id='imgBlkFront')
            if amz_img:
                # Prefer the high-res image if available, otherwise take the standard src
                image = amz_img.get('data-old-hires') or amz_img.get('src')
                
        # 3. Final safety net
        if not image:
            image = "https://placehold.co/200x200?text=No+Image"
        
        price_el = soup.find(string=re.compile(r'₹[0-9,]+'))
        price = price_el.strip() if price_el else "Price on Site"
        
        clean_title = raw_title.split('|')[0].split(':')[0].split('- Buy')[0].strip()
        
        stop_words = ["with", "for", "men", "women", "the", "and", "buy", "online", "ml", "gm"]
        clean_words = [w for w in clean_title.split() if w.lower() not in stop_words]
        
        search_query = " ".join(clean_words[:4]) 
        
        base_data = {
            "site": site,
            "title": clean_title,
            "price": price,
            "reviews": "Direct Link",
            "image": image,
            "link": url
        }
        
        return base_data, search_query
    except Exception as e:
        print(f"Direct Link Error: {e}")
        return None, None
    finally:
        if driver: driver.quit()
def scrape_all_sites(query):
    driver = None
    try:
        driver = get_stealth_driver()
        
        # 1. Open Amazon in Tab 1
        url_amz = f"https://www.amazon.in/s?k={query.replace(' ', '+')}&ref=nb_sb_noss"
        try: driver.get(url_amz)
        except: pass 
        tab_amz = driver.current_window_handle

        time.sleep(2) # HUMAN DELAY: Wait 2 seconds before opening the next tab

        # 2. Open Flipkart in Tab 2
        driver.switch_to.new_window('tab')
        url_flp = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        try: driver.get(url_flp)
        except: pass
        tab_flp = driver.current_window_handle

        time.sleep(2) # HUMAN DELAY: Wait 2 seconds before opening the next tab

        # 3. Open Nykaa in Tab 3
        driver.switch_to.new_window('tab')
        url_nyk = f"https://www.nykaa.com/search/result/?q={query.replace(' ', '+')}"
        try: driver.get(url_nyk)
        except: pass
        tab_nyk = driver.current_window_handle

        # RELAXED WAIT: Give the network 5 seconds to finish rendering
        time.sleep(5) 

        # Harvest Data: Switch tab -> SCROLL TO FAKE HUMAN ACTIVITY -> Read HTML
        driver.switch_to.window(tab_amz)
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(1)
        amazon_data = extract_amazon(driver.page_source, query)

        driver.switch_to.window(tab_flp)
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(1)
        flipkart_data = extract_flipkart(driver.page_source, query)

        driver.switch_to.window(tab_nyk)
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(1)
        nykaa_data = extract_nykaa(driver.page_source, query)

        return [amazon_data, flipkart_data, nykaa_data]

    except Exception as e:
        print(f"Master Scraper Error: {e}")
        return []
    finally:
        if driver: driver.quit()

import json # MAKE SURE THIS IS AT THE TOP OF YOUR FILE

def get_ai_recommendation(all_data):
    context = ""
    bad_titles = ["Title Unknown", "Item not on website", "Error", "Blocked by Bot Check", "Product Not Found"]
    
    for d in all_data:
        if d and d['title'] not in bad_titles:
            context += f"Source: {d['site']} | Product: {d['title']} | Price: {d['price']} | Feedback: {d['reviews']}\n"
        elif d:
            context += f"Source: {d['site']} | Status: MISSING_OR_BLOCKED\n"
    
    # Force Gemini to return a strict JSON object
    prompt = f"""
    Analyze these shopping results:
    {context}
    
    You must respond with a strictly valid JSON object containing exactly three keys: "Amazon", "Flipkart", and "Nykaa".
    For each key, write a 1-sentence review of the deal on that platform.
    If the context says the status is MISSING_OR_BLOCKED for a platform, the value for that key MUST be exactly: "No review."
    Do not output any markdown formatting or extra text. Just the JSON object.
    """
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        # Strip out potential markdown backticks that Gemini sometimes hallucinates
        raw_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_text)
    except Exception as e:
        print(f"AI Parse Error: {e}")
        return {"Amazon": "AI Error.", "Flipkart": "AI Error.", "Nykaa": "AI Error."}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_input = request.form.get('product_name')
        
        if not user_input or user_input.strip() == "":
            return render_template('index.html', results=None, verdict=None)
        
        query = user_input
        base_product = None
        
        if user_input.startswith('http'):
            base_product, query = scrape_direct_product(user_input)
            if not base_product:
                return render_template('index.html', results=None, verdict=None, error="Could not read link.")
        
        results = scrape_all_sites(query)
        
        if not results:
            return render_template('index.html', results=None, verdict=None, error="Scraper failed.")

        if base_product:
            final_results = []
            for res in results:
                if res and res['site'].lower() == base_product['site'].lower():
                    final_results.append(base_product)
                else:
                    final_results.append(res)
            results = final_results

        # Pass ALL results to the AI so it knows which ones are missing
        verdict_dict = get_ai_recommendation(results)
            
        return render_template('index.html', results=results, verdict=verdict_dict, query=user_input)
        
    return render_template('index.html', results=None, verdict=None)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)