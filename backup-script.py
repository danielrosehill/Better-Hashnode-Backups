import requests
import os
import re
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables with hardcoded API URL
HASHNODE_API = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_TOKEN")
HASHNODE_USERNAME = os.getenv("HASHNODE_USERNAME")
HASHNODE_BLOG_URL = os.getenv("HASHNODE_BLOG_URL")
BACKUP_PATH = os.getenv("BACKUP_PATH", "posts")

# Print configuration for debugging
print("Configuration:")
print(f"API URL: {HASHNODE_API}")
print(f"Username: {HASHNODE_USERNAME}")
print(f"Blog URL: {HASHNODE_BLOG_URL}")
print(f"Backup Path: {BACKUP_PATH}")

def get_hashnode_posts():
    query = f"""
    {{
        user(username: "{HASHNODE_USERNAME}") {{
            publications(first: 10) {{
                edges {{
                    node {{
                        posts(first: 50) {{
                            edges {{
                                node {{
                                    title
                                    slug
                                    publishedAt
                                    content {{
                                        markdown
                                    }}
                                    tags {{
                                        name
                                    }}
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }}
    }}
    """
    
    headers = {
        "Authorization": f"{HASHNODE_TOKEN}",
        "Content-Type": "application/json",
    }
    
    response = requests.post(HASHNODE_API, json={"query": query}, headers=headers)
    
    # Debug information
    print(f"API Response Status Code: {response.status_code}")
    print(f"API Response Content: {response.text[:500]}...")
    
    response_json = response.json()
    
    if "errors" in response_json:
        print(f"API returned errors: {response_json['errors']}")
        raise Exception(f"Hashnode API error: {response_json['errors']}")
        
    if "data" not in response_json:
        print(f"Unexpected API response structure: {response_json}")
        raise Exception("API response missing 'data' field")
    
    # Navigate the new response structure
    posts = []
    publications = response_json["data"]["user"]["publications"]["edges"]
    for pub in publications:
        pub_posts = pub["node"]["posts"]["edges"]
        for post in pub_posts:
            post_data = post["node"]
            # Adjust the post data structure to match what the rest of the code expects
            post_data["dateAdded"] = post_data["publishedAt"]
            post_data["contentMarkdown"] = post_data["content"]["markdown"]
            posts.append(post_data)
    
    return posts

def extract_image_urls(content):
    # Updated patterns to match Hashnode's specific format
    markdown_pattern = r'!\[.*?\]\((.*?)(?:\s+align=".*?")?\)'  # Handle optional align attribute
    html_pattern = r'<img[^>]+src="([^">]+)"'
    
    urls = []
    urls.extend(re.findall(markdown_pattern, content))
    urls.extend(re.findall(html_pattern, content))
    
    # Clean up URLs (remove align attributes if they got caught)
    cleaned_urls = [url.split(' align=')[0].strip() for url in urls]
    
    # Only allow specific image formats
    allowed_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    filtered_urls = []
    
    for url in cleaned_urls:
        lower_url = url.lower()
        if any(lower_url.endswith(ext) for ext in allowed_extensions):
            filtered_urls.append(url)
        else:
            print(f"Skipping non-supported image format: {url}")
    
    print(f"Found URLs: {filtered_urls}")  # Debug print
    return filtered_urls

def download_image(url, post_path):
    try:
        # Verify allowed format again
        allowed_extensions = ('.jpg', '.jpeg', '.png', '.webp')
        if not any(url.lower().endswith(ext) for ext in allowed_extensions):
            print(f"Skipping non-supported image format: {url}")
            return None
            
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename or '.' not in filename:
            ext = response.headers.get('content-type', '').split('/')[-1]
            if ext == 'jpeg':
                ext = 'jpg'
            filename = f"image_{hash(url)}.{ext}"
        
        image_dir = os.path.join(post_path, "images")
        os.makedirs(image_dir, exist_ok=True)
        
        image_path = os.path.join(image_dir, filename)
        
        # Write image to file
        with open(image_path, 'wb') as f:
            f.write(response.content)
        
        print(f"Successfully downloaded: {filename}")
        return url
        
    except requests.exceptions.Timeout:
        print(f"Timeout downloading image {url}")
        return None
    except Exception as e:
        print(f"Failed to download image {url}: {e}")
        return None

def create_frontmatter(post):
    metadata = {
        "title": post["title"],
        "date": datetime.fromisoformat(post["dateAdded"]).strftime("%Y-%m-%d"),
        "tags": [tag["name"] for tag in post["tags"]],
        "slug": post["slug"],
        "canonical_url": f"https://{HASHNODE_BLOG_URL}/{post['slug']}"
    }
    
    # Create the frontmatter string
    fm_string = "---\n"
    fm_string += yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    fm_string += "---\n\n"
    
    # Add the content
    fm_string += post["contentMarkdown"]
    
    return fm_string

def backup_posts():
    posts = get_hashnode_posts()
    
    for post in posts:
        print(f"\nProcessing post: {post['title']}")
        
        # First, save the markdown file
        post_slug = post['slug']
        post_dir = os.path.join(BACKUP_PATH, post_slug)
        os.makedirs(post_dir, exist_ok=True)
        
        # Write markdown file immediately
        file_content = create_frontmatter(post)
        file_path = os.path.join(post_dir, "index.md")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
        print(f"Saved post to: {file_path}")
        
        # Then handle images
        image_urls = extract_image_urls(post["contentMarkdown"])
        print(f"Found {len(image_urls)} supported images")
        
        for url in image_urls:
            print(f"Downloading image: {url}")
            download_image(url, post_dir)

def main():
    try:
        print("Starting Hashnode blog backup")
        print(f"Username: {HASHNODE_USERNAME}")
        print(f"Blog URL: {HASHNODE_BLOG_URL}")
        print(f"Backup Path: {BACKUP_PATH}")
        
        # Verify environment variables
        required_vars = [
            "HASHNODE_TOKEN", 
            "HASHNODE_USERNAME", 
            "HASHNODE_BLOG_URL"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        backup_posts()
        print("Backup completed successfully")
        
    except Exception as e:
        print(f"Error during backup: {str(e)}")
        raise

if __name__ == "__main__":
    main()