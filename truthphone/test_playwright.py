from agent import _run_playwright_search_sync

if __name__ == "__main__":
    print("Starting Playwright Test...")
    text = _run_playwright_search_sync("Samsung 5G phone under 30k for daily use")
    if text:
        print(f"SUCCESS! Extracted {len(text)} characters of text.")
        print("First 500 chars:")
        print(text[:500])
    else:
        print("FAILED to extract text.")
