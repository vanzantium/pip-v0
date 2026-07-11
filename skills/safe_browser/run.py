#!/usr/bin/env python3
import argparse
import sys
from typing import Any

def get_page_text(page):
    # Extract readable text from the page
    return page.evaluate("() => document.body.innerText")

def safe_browser_read(args: argparse.Namespace) -> dict[str, Any]:
    url = getattr(args, "url", "")
    if not url:
        return {"skill": "safe_browser_read", "ok": False, "message": "No URL provided"}
        
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Open visible browser so the user sees what Pip is doing
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            
            text = get_page_text(page)
            # Truncate text to avoid massive outputs
            text = text[:8000] if text else ""
            
            browser.close()
            return {"skill": "safe_browser_read", "ok": True, "url": url, "content": text}
    except Exception as e:
        return {"skill": "safe_browser_read", "ok": False, "message": str(e)}

def safe_browser_search(args: argparse.Namespace) -> dict[str, Any]:
    query = getattr(args, "query", "")
    if not query:
        return {"skill": "safe_browser_search", "ok": False, "message": "No query provided"}
        
    try:
        import urllib.parse
        from playwright.sync_api import sync_playwright
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(search_url, wait_until="networkidle")
            
            text = get_page_text(page)
            text = text[:8000] if text else ""
            
            browser.close()
            return {"skill": "safe_browser_search", "ok": True, "query": query, "content": text}
    except Exception as e:
        return {"skill": "safe_browser_search", "ok": False, "message": str(e)}

def run(args: argparse.Namespace) -> dict[str, Any]:
    skill_name = getattr(args, "skill", "")
    
    if skill_name == "safe_browser_read":
        return safe_browser_read(args)
    elif skill_name == "safe_browser_search":
        return safe_browser_search(args)
        
    return {"skill": "safe_browser", "ok": False, "error": f"Unknown skill {skill_name}"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", type=str)
    parser.add_argument("--url", type=str)
    parser.add_argument("--query", type=str)
    args = parser.parse_args()
    print(run(args))
