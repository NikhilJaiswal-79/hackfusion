import asyncio
import sys
import os

# Set up utf-8
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from langchain_core.messages import HumanMessage
from agent import app

async def test():
    print("Testing the graph...")
    inputs = {"messages": [HumanMessage(content="Samsung 5G phone under 30k for daily use")], "current_phase": "search"}
    try:
        config = {"configurable": {"thread_id": "test_thread_123"}}
        result = await app.ainvoke(inputs, config)
        print("\n\nFINAL RESULT:")
        print(result)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
