import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

import os
import shutil
import time
import re
from flask import Flask, render_template, request
from bs4 import BeautifulSoup
import google.generativeai as genai
import undetected_chromedriver as uc

app = Flask(__name__)

# --- CLEANUP (Forces a fresh start and fixes FileExistsError) ---
driver_cache = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
if os.path.exists(driver_cache):
    try:
        shutil.rmtree(driver_cache)
    except:
        pass

# --- CONFIGURATION ---
# Replace with your actual Gemini API Key from Google AI Studio
genai.configure(api_key="AIzaSyBVa0VmN7wezfnAsCSBgi3ZlIwi1KRnm-c")
MODEL = genai.GenerativeModel('gemini-1.5-flash')

def get_fast_driver():
    options = uc.ChromeOptions()
    # Pushes window off-screen to avoid detection and stay out of your way
    options.add_argument("--window-position=-32000,-32000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.page_load_strategy = 'eager' 
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    # use_subprocess=True is mandatory for modern bot bypass
    return uc.Chrome(options=options, use_subprocess=True)

# --- SCRAPERS ---
def scrape_amazon(query):
    driver = get_fast_driver()
    search_url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
    try:
        driver.get(search_url)
        time.sleep(6) # Essential wait for anti-bot check
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        item = soup.find('div', {'data-component-type': 's-search-result'})
        
        if not item:
            return {"platform": "Amazon", "title": "Not Found (Blocked)", "price": "N/A", "rating": "N/A", "url": search_url}

        title_el = item.select_one('h2 span.a-text-normal, span.a-size-medium')
        price_el = item.select_one('span.a-price-whole')
        rating_el = item.select_one('span.a-icon-alt')
        
        return {
            "platform": "Amazon",
            "title": title_el.text.strip() if title_el else "Not Found",
            "price": f"₹{price_el.text.strip()}" if price_el else "N/A",
            "rating": rating_el.text.strip().split()[0] if rating_el else "N/A",
            "url": search_url
        }
    except Exception as e:
        return {"platform": "Amazon", "error": str(e)}
    finally:
        driver.quit()

def scrape_flipkart(query):
    driver = get_fast_driver()
    search_url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
    try:
        driver.get(search_url)
        time.sleep(6)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        item = soup.find('div', attrs={'data-id': True})
        
        if not item:
            return {"platform": "Flipkart", "title": "Not Found (Blocked)", "price": "N/A", "rating": "N/A", "url": search_url}

        title_el = item.select_one('div.KzDlHZ, div._4rR01T, a.wjcEIp, img[alt]')
        price_el = item.select_one('div.Nx9bqj, div._30jeq3, div.hl05eU')
        rating_el = item.select_one('div.XQDdHH, div._3LWZlK')
        
        title = title_el.text.strip() if title_el and title_el.text else (item.find('img')['alt'] if item.find('img') else "Not Found")

        return {
            "platform": "Flipkart",
            "title": title,
            "price": price_el.text.strip() if price_el else "N/A",
            "rating": rating_el.text.strip() if rating_el else "N/A",
            "url": search_url
        }
    except Exception as e:
        return {"platform": "Flipkart", "error": str(e)}
    finally:
        driver.quit()

def get_ai_verdict(amazon_data, flipkart_data):
    if "Not Found" in amazon_data.get('title', '') and "Not Found" in flipkart_data.get('title', ''):
        return "Verdict: No data available.\nScore: 0"
    
    prompt = f"Compare: Amazon: {amazon_data.get('title')} ({amazon_data.get('price')}) vs Flipkart: {flipkart_data.get('title')} ({flipkart_data.get('price')}). 1 sentence verdict and score/10."
    try:
        response = MODEL.generate_content(prompt)
        return response.text
    except:
        return "Verdict: AI Analysis failed.\nScore: N/A"

# --- ROUTES ---
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', data=None)

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('product_name')
    
    # SEQUENTIAL SCRAPING to prevent FileExistsError
    amazon_data = scrape_amazon(query)
    flipkart_data = scrape_flipkart(query)
        
    ai_analysis = get_ai_verdict(amazon_data, flipkart_data)
    
    result_data = {
        "query": query,
        "amazon": amazon_data,
        "flipkart": flipkart_data,
        "ai": ai_analysis
    }
    return render_template('index.html', data=result_data)

if __name__ == '__main__':
    app.run(debug=True)