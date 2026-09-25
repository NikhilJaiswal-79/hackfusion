import os
import sys
import logging
import asyncio
import traceback

os.environ["PYTHONIOENCODING"] = "utf-8"

# Load GROQ_API_KEY from environment or local .env file
if not os.getenv("GROQ_API_KEY"):
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GROQ_API_KEY="):
                    os.environ["GROQ_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

from browser_use import Agent as BrowserAgent
from browser_use.llm import ChatGroq as BrowserChatGroq
from browser_use.browser.browser import Browser, BrowserConfig

async def test():
    try:
        print("Testing ChatGroq with openai/gpt-oss-20b and headless=False...")
        llm = BrowserChatGroq(model="openai/gpt-oss-20b", temperature=0.2)
        browser = Browser(config=BrowserConfig(headless=False))
        agent = BrowserAgent(
            task="Go to https://www.amazon.in and search for samsung 5g phone",
            llm=llm,
            browser=browser
        )
        res = await agent.run()
        print("\nSUCCESS! Result:", res.final_result())
    except Exception as e:
        print("\nERROR OCCURRED:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
