from flask import Flask, render_template, request, jsonify, Response, abort
import requests
from bs4 import BeautifulSoup
import re
import json
import urllib.parse
import logging  # Added for debugging

app = Flask(__name__)

# Global variables for pagination
VIDEOS_PER_PAGE = 20

# Example proxies setup - replace with your actual proxy
proxies = {
    'http': 'http://frfafccu:etme5j7m3bir@142.111.48.253:7030',
    'https': 'http://frfafccu:etme5j7m3bir@142.111.48.253:7030',
}

# Set up logging
logging.basicConfig(level=logging.DEBUG)  # Logs to console; adjust as needed

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    search_term = request.form.get('search_term', '')
    filter_type = request.form.get('filter_type', 'relevance')
    
    if request.method == 'POST' and not request.is_json and search_term:
        results = fetch_videos(search_term, filter_type, page=1)
        logging.debug(f"Initial search results for term '{search_term}' and filter '{filter_type}': {len(results)} items")
    
    return render_template('index.html', results=results, search_term=search_term, 
                          filter_type=filter_type, current_page=1)

@app.route('/load_more', methods=['POST'])
def load_more():
    search_term = request.json.get('search_term', '')
    filter_type = request.json.get('filter_type', 'relevance')
    page = request.json.get('page', 1)
    
    if search_term:
        results = fetch_videos(search_term, filter_type, page)
        logging.debug(f"Load more results for term '{search_term}', filter '{filter_type}', page {page}: {len(results)} items")
        return jsonify({'results': results})
    return jsonify({'results': []})

@app.route('/get_video_source', methods=['POST'])
def get_video_source():
    video_url = request.json.get('video_url', '')
    if not video_url:
        logging.error("No URL provided in get_video_source")
        return jsonify({'error': 'No URL provided'}), 400
    
    video_source = fetch_video_source(video_url)
    if video_source:
        logging.debug(f"Video source fetched successfully for URL: {video_url}")
        return jsonify({'video_source': video_source})
    else:
        logging.error(f"Could not find video source for URL: {video_url}")
        return jsonify({'error': 'Could not find video source'}), 404

@app.route('/proxy_video')
def proxy_video():
    url = request.args.get('url')
    if not url:
        logging.error("No URL provided in proxy_video")
        return "No URL provided", 400
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.pornhub.com/'
        }
        response = requests.get(url, stream=True, headers=headers, timeout=15, proxies=proxies)
        response.raise_for_status()
        
        if url.lower().endswith('.m3u8'):
            content = response.text
            return Response(content, content_type='application/vnd.apple.mpegurl')
        else:
            def generate():
                for chunk in response.iter_content(chunk_size=1024):
                    yield chunk
            return Response(generate(), content_type=response.headers.get('content-type', 'video/mp4'))
    
    except requests.RequestException as e:
        logging.error(f"Request exception in proxy_video: {str(e)}")
        abort(404, description=f"Error fetching video: {str(e)}")
    except Exception as e:
        logging.error(f"General exception in proxy_video: {str(e)}")
        abort(500, description=f"Server error: {str(e)}")

def fetch_videos(search_term, filter_type='relevance', page=1):
    formatted_search = search_term.replace(' ', '+')
    base_url = "https://www.pornhub.com/video/search?search="
    filter_params = ""
    
    if filter_type == 'most_viewed':
        filter_params = "&o=mv"
    elif filter_type == 'top_rated':
        filter_params = "&o=tr"
    elif filter_type == 'newest':
        filter_params = "&o=cm"
    elif filter_type == 'longest':
        filter_params = "&o=lg"
    
    page_param = f"&page={page}"
    url = f"{base_url}{formatted_search}{filter_params}{page_param}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
        if response.status_code == 200:
            results = parse_videos(response.text)
            logging.debug(f"Parsed {len(results)} videos from page {page}")
            return results[:VIDEOS_PER_PAGE]  # Ensure we only return the required number
        else:
            logging.error(f"Failed to fetch page {page}: Status code {response.status_code}")
            return []
    except Exception as e:
        logging.error(f"Error in fetch_videos for page {page}: {str(e)}")
        return []

def parse_videos(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    video_elements = soup.select('.videoBox')
    
    results = []
    seen_video_ids = set()  # To avoid duplicates in the same page response
    for video in video_elements:
        try:
            link_element = video.select_one('a')
            img_element = video.select_one('img')
            
            if link_element and img_element:
                video_url = "https://www.pornhub.com" + link_element['href'] if link_element.has_attr('href') else ""
                video_id = link_element['href'].split('=')[-1] if '=' in link_element['href'] else ""
                
                if video_id in seen_video_ids:  # Skip duplicates on the same page
                    continue
                seen_video_ids.add(video_id)
                
                title = img_element['alt'] if img_element.has_attr('alt') else "No title"
                thumbnail = img_element['data-src'] if img_element.has_attr('data-src') else img_element['src'] if img_element.has_attr('src') else ""
                duration_element = video.select_one('.duration')
                duration = duration_element.text.strip() if duration_element else "Unknown"
                views_element = video.select_one('.views')
                views = views_element.text.strip() if views_element else "Unknown"
                rating_element = video.select_one('.rating-container .value')
                rating = rating_element.text.strip() if rating_element else "N/A"
                hd_element = video.select_one('.hd-thumbnail')
                is_hd = True if hd_element else False
                
                results.append({
                    "title": title,
                    "thumbnail": thumbnail,
                    "video_url": video_url,
                    "video_id": video_id,
                    "duration": duration,
                    "views": views,
                    "rating": rating,
                    "is_hd": is_hd
                })
        except Exception as e:
            logging.debug(f"Skipped video due to parsing error: {str(e)}")
            continue
    return results

def fetch_video_source(video_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(video_url, headers=headers, timeout=15, proxies=proxies)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # ... (rest of the function remains the same)
    except Exception as e:
        logging.error(f"Error in fetch_video_source: {str(e)}")
        return None

if __name__ == '__main__':
    app.run(debug=True)