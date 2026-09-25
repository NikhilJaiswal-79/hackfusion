from playwright.sync_api import sync_playwright

def test_amazon():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.amazon.in", timeout=60000)
        page.locator("#twotabsearchtextbox").click()
        page.locator("#twotabsearchtextbox").press_sequentially("Samsung 5G phone under 30k", delay=100)
        page.click("#nav-search-submit-button")
        page.wait_for_timeout(3000)
        
        links = page.evaluate('''() => {
            let allLinks = Array.from(document.querySelectorAll('a'));
            let dpLinks = allLinks.map(a => a.href).filter(h => h && h.includes('/dp/'));
            return [...new Set(dpLinks)].slice(0, 5);
        }''')
        print(f"Extracted links: {links}")
        browser.close()

test_amazon()
