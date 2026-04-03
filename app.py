import os
import shutil
import time
import re
from flask import Flask, render_template, request
from bs4 import BeautifulSoup
from google import genai  # Updated library
import undetected_chromedriver as uc

app = Flask(__name__)

# --- CLEANUP ---
driver_cache = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
if os.path.exists(driver_cache):
    try:
        shutil.rmtree(driver_cache, ignore_errors=True)
    except:
        pass

# --- CONFIGURATION ---
client = genai.Client(api_key="AIzaSyBz0z_OyXYHYBj71bTjWiJ3tD8VW1HnlU8")
MODEL_ID = 'gemini-2.5-pro'

def get_stealth_driver():
    options = uc.ChromeOptions()
    # options.add_argument("--window-position=-32000,-32000") # Keep visible for CAPTCHAs
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.page_load_strategy = 'eager'
    
    # STRICT ENFORCEMENT. No fallback. 
    driver = uc.Chrome(options=options, use_subprocess=True, version_main=146)
    return driver

def scrape_amazon(query):
    driver = get_stealth_driver()
    try:
        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}&ref=nb_sb_noss"
        driver.get(url)
        time.sleep(8)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Get ALL items on the page
        items = soup.find_all('div', {'data-component-type': 's-search-result'})
        if not items:
            if "api-services-support@amazon.com" in driver.page_source or "Robot Check" in driver.page_source:
                return {"site": "Amazon", "title": "Blocked by CAPTCHA", "price": "N/A", "reviews": "Solve puzzle", "image": "", "link": "#"}
            return {"site": "Amazon", "title": "Not Found", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}

        # 2. Loop through and SKIP the sponsored ads
        target_item = None
        for item in items:
            is_sponsored = item.find(string=re.compile(r'Sponsored', re.IGNORECASE))
            if not is_sponsored:
                target_item = item
                break # Found the first organic result

        if not target_item:
            target_item = items[0] # Fallback if everything is an ad

        # 3. Extract data from the organic item
        title_el = target_item.select_one('h2 span, span.a-text-normal')
        title = title_el.text.strip() if title_el else "Title Unknown"

        price_el = target_item.select_one('span.a-price-whole')
        price = f"₹{price_el.text.strip()}" if price_el else "Price Unknown"

        review_el = target_item.select_one('span.a-icon-alt')
        reviews = review_el.text.strip().split(' ')[0] if review_el else "No Ratings"

        a_tag = target_item.select_one('h2 a')
        link = "https://www.amazon.in" + a_tag['href'] if a_tag and 'href' in a_tag.attrs else "#"
        
        img_tag = target_item.select_one('img.s-image')
        image = img_tag['src'] if img_tag else "https://via.placeholder.com/150?text=No+Image"

        return {"site": "Amazon", "title": title, "price": price, "reviews": reviews, "image": image, "link": link}
    except Exception as e:
        return {"site": "Amazon", "title": "Error", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}
    finally: driver.quit()

def scrape_flipkart(query):
    driver = get_stealth_driver()
    try:
        url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        driver.get(url)
        time.sleep(8)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Get ALL items on the page
        items = soup.find_all('div', attrs={'data-id': True})
        if not items: return {"site": "Flipkart", "title": "Not Found", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}

        # 2. Loop through and SKIP the ads
        target_item = None
        for item in items:
            # Flipkart puts a tiny "Ad" text on sponsored products
            is_ad = item.find(string=re.compile(r'^Ad$', re.IGNORECASE))
            if not is_ad:
                target_item = item
                break

        if not target_item:
            target_item = items[0]

        # 3. Extract using Regex
        title_el = target_item.select_one('a[title], a.WkTcLC, a.IRpwTa, div.KzDlHZ')
        title = title_el['title'] if title_el and 'title' in title_el.attrs else (title_el.text.strip() if title_el else "Title Unknown")

        price_el = target_item.select_one('div.Nx9bqj, div._30jeq3')
        if not price_el:
            price_el = target_item.find(string=re.compile(r'^₹[0-9,]+$'))
        
        if hasattr(price_el, 'text'): price = price_el.text.strip()
        elif price_el: price = str(price_el).strip()
        else: price = "Price Unknown"

        review_el = target_item.select_one('div.XQDdHH, div._3LWZlK')
        reviews = review_el.text.strip() if review_el else "No Ratings"

        a_tag = target_item.select_one('a')
        raw_link = a_tag['href'] if a_tag and 'href' in a_tag.attrs else "#"
        link = raw_link if raw_link.startswith('http') else "https://www.flipkart.com" + raw_link if raw_link != "#" else "#"

        img_tag = target_item.select_one('img')
        image = img_tag['src'] if img_tag and 'src' in img_tag.attrs else "https://via.placeholder.com/150?text=No+Image"

        return {"site": "Flipkart", "title": title, "price": price, "reviews": reviews, "image": image, "link": link}
    except Exception as e:
        return {"site": "Flipkart", "title": "Error", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}
    finally: driver.quit()

def scrape_nykaa(query):
    driver = get_stealth_driver()
    try:
        url = f"https://www.nykaa.com/search/result/?q={query.replace(' ', '+')}"
        driver.get(url)
        time.sleep(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Get all product links
        item_links = soup.find_all('a', href=re.compile(r'/p/'))
        if not item_links: 
            return {"site": "Nykaa", "title": "Not Found", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}

        # Skip carousels, find the first valid card with a price
        target_card = None
        target_link = None
        for item_link in item_links:
            card = item_link.find_parent('div', class_=re.compile(r'css-.*')) or item_link.parent
            if card.find(string=re.compile(r'₹')):
                target_card = card
                target_link = item_link
                break

        if not target_card:
            return {"site": "Nykaa", "title": "Not Found", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}

        title_el = target_card.find('h2') or target_card.find('div', class_=re.compile(r'title|name|xrzm88'))
        title = title_el.text.strip() if title_el else "Title Unknown"

        price_el = target_card.find(string=re.compile(r'₹'))
        price = price_el.strip() if price_el else "Price Unknown"

        raw_link = target_link['href']
        link = raw_link if raw_link.startswith('http') else "https://www.nykaa.com" + raw_link

        img_tag = target_card.find('img')
        image = img_tag['src'] if img_tag and 'src' in img_tag.attrs else "https://via.placeholder.com/150?text=No+Image"

        return {"site": "Nykaa", "title": title, "price": price, "reviews": "Check Site", "image": image, "link": link}
        
    except Exception as e:
        return {"site": "Nykaa", "title": f"Error", "price": "N/A", "reviews": "N/A", "image": "", "link": "#"}
    finally: driver.quit()

def get_ai_recommendation(all_data):
    context = ""
    for d in all_data:
        if d:
            context += f"Source: {d['site']} | Product: {d['title']} | Price: {d['price']} | Feedback: {d['reviews']}\n"
    
    prompt = f"""
    Analyze these shopping results:
    {context}
    
    1. Identify the 'Best Value' item.
    2. Summarize why it's better than others (mention price and review sentiment).
    3. If it's a cosmetic, check if Nykaa has a better reputation for authenticity.
    Format your response as a clear recommendation for a buyer.
    """
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"AI Error: {e}")
        return "AI analysis failed. Please compare manually."

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        query = request.form.get('product_name')
        
        amazon = scrape_amazon(query)
        flipkart = scrape_flipkart(query)
        nykaa = scrape_nykaa(query)
        
        results = [amazon, flipkart, nykaa]
        # Added "Error" to the filter list so broken sites don't feed garbage to the AI
        valid_results = [r for r in results if r and "Unknown" not in r['title'] and "Not Found" not in r['title'] and "Error" not in r['title']]
        
        if not valid_results:
            verdict = "All sites blocked the connection. Please solve the CAPTCHAs in the popup windows or try a different network."
        else:
            verdict = get_ai_recommendation(valid_results)
            
        return render_template('index.html', results=results, verdict=verdict, query=query)
        
    return render_template('index.html', results=None)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)