import asyncio
import traceback

def _run_playwright_search_sync(query: str) -> str:
    from playwright.sync_api import sync_playwright
    import urllib.parse
    
    print(f"\n🌐 --> Opening Chrome to search Amazon for: {query}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            # VISUAL HACKATHON FEATURE: Start from Google and type amazon.in
            print("🌐 Navigating to Google first...")
            page.goto("https://www.google.com", timeout=60000)
            page.wait_for_timeout(1000)
            
            print("⌨️ Typing amazon.in into Google...")
            # Google's search box is usually a textarea named 'q'
            page.locator("textarea[name='q']").click()
            page.locator("textarea[name='q']").press_sequentially("amazon.in", delay=100)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            
            print("🖱️ Clicking Amazon link...")
            page.locator("a[href*='amazon.in']").first.click()
            page.wait_for_timeout(3000)
            
            # Physically type into the Amazon search bar like a human
            print(f"⌨️ Typing query into Amazon search bar...")
            page.locator("#twotabsearchtextbox").click()
            page.locator("#twotabsearchtextbox").press_sequentially(query, delay=100)
            page.wait_for_timeout(1000)
            
            # Click the search button
            print(f"🖱️ Clicking search...")
            page.click("#nav-search-submit-button")
            
            # Wait for search results to load
            page.wait_for_timeout(3000)
            
            # VISUAL HACKATHON FEATURE: Scroll smoothly through Amazon results so it looks like reading
            print("👀 Visually scrolling through Amazon results...")
            for _ in range(4):
                page.evaluate("window.scrollBy(0, 700)")
                page.wait_for_timeout(1000)
            
            # Get the main search text FIRST before navigating away
            main_text = page.evaluate("document.body.innerText")
            
            # Extract the actual product titles and URLs
            products_data = []
            try:
                products_data = page.evaluate('''() => {
                    let items = Array.from(document.querySelectorAll('.s-result-item[data-asin]:not([data-asin=""])'));
                    return items.slice(0, 5).map(item => {
                        let a = item.querySelector('a[href*="/dp/"]');
                        let titleText = a ? a.innerText.trim() : "";
                        if (!titleText && item.innerText) {
                            titleText = item.innerText.split('\\n')[0];
                        }
                        return {title: titleText || "Samsung Galaxy Phone", url: a ? a.href : ""};
                    }).filter(p => p.url !== "");
                }''')
            except Exception as e:
                print(f"Error extracting data: {e}")
                
            # VISUAL HACKATHON FEATURE: Go to the product page, scroll, and come back!
            for prod in products_data:
                print(f"👀 Visually inspecting product: {prod['title'][:25]}...")
                try:
                    page.goto(prod['url'], timeout=20000)
                    page.wait_for_timeout(2000)
                    page.evaluate("window.scrollBy(0, 800)") # Scroll down
                    page.wait_for_timeout(2000) # Wait at the bottom
                    page.go_back(timeout=20000) # COME BACK!
                    page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"[VISUAL_HACK] Skipped visual reading: {e}")
            
            # Return the EXACT links at the TOP so the LLM cannot miss them
            formatted_urls = "\n".join([f"Phone: {p['title']}\nURL: {p['url']}" for p in products_data])
            return f"--- EXACT PHONES WITH URLS ---\n{formatted_urls}\n\n--- RAW SEARCH TEXT ---\n{main_text[:10000]}"
        except Exception as e:
            print(f"[PLAYWRIGHT ERROR] {e}")
            import traceback
            traceback.print_exc()
            return ""
        finally:
            browser.close()

if __name__ == "__main__":
    res = _run_playwright_search_sync("Samsung 5G phone under 30k")
    print(res[:500])
