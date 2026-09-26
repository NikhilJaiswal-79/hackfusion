import os
import sys
import asyncio
import traceback

# Fix Windows console encoding (cp1252 can't handle emoji from LLM responses)
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import logging
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_groq import ChatGroq as LangchainChatGroq
from langgraph.graph import StateGraph, START, END
from browser_use import Agent as BrowserAgent
from browser_use.llm import ChatGroq as BrowserChatGroq
from browser_use.browser.browser import Browser, BrowserConfig
from pydantic import BaseModel, Field

# Fix Python logging encoding for Windows cp1252 emoji issue
class UTF8StreamHandler(logging.StreamHandler):
    def __init__(self, stream=None):
        super().__init__(stream or sys.stdout)
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

logging.basicConfig(level=logging.INFO, handlers=[UTF8StreamHandler()])

from state import AgentState, PhoneCandidate, VerificationClaim, VerificationResult

# Load GROQ_API_KEY from environment or local .env file
if not os.getenv("GROQ_API_KEY"):
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GROQ_API_KEY="):
                    os.environ["GROQ_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

# LangChain LLM for conversation / structured output
# NOTE: openai/gpt-oss-20b doesn't support tool calling — never bind tools to these
llm = LangchainChatGroq(model="openai/gpt-oss-20b", temperature=0.3)
llm_structured = LangchainChatGroq(model="openai/gpt-oss-20b", temperature=0.0)

# browser-use requires its own wrapper
# Using the 120b model because 20b fails to format JSON reliably for autonomous browsing
llm_browser = BrowserChatGroq(model="openai/gpt-oss-120b", temperature=0.2)


# ── Utility ────────────────────────────────────────────────────────────────────
def extract_text(content) -> str:
    """Safely extract plain text from any Gemini response content format."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and "text" in p:
                parts.append(p["text"])
        return " ".join(parts)
    return str(content)


# ── Agent 1: Conversation / Clarification ─────────────────────────────────────
async def conversation_node(state: AgentState):
    """Manages dialogue state, asks clarifying questions one-by-one."""
    system_prompt = """You are the Conversation Agent for TruthPhone, a guided smartphone buying and fact-check assistant.
Your job is to clarify what smartphone the user wants.
You ideally want to know: budget range, brand preference, use case, and 4G vs 5G.

Rules:
- Ask questions ONE at a time.
- NEVER ask the same question twice. NEVER ask for budget if it was already mentioned.
- Do NOT output any system commands, function calls, tool calls, or JSON. YOU MUST RESPOND ONLY IN PLAIN CONVERSATIONAL TEXT.
- The user will manually initiate the search when they are ready. Just converse patiently."""

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await llm.ainvoke(messages)
    text = extract_text(response.content)

    return {
        "messages": [AIMessage(content=text)],
        "current_phase": "clarification",
    }

# ── Helper to run Playwright Scraper safely on Windows Uvicorn ─────────────
def _run_playwright_search_sync(query: str) -> str:
    """Runs a hardcoded Playwright scraper in a separate thread to bypass Windows asyncio bugs."""
    from playwright.sync_api import sync_playwright
    import urllib.parse
    
    print(f"\n🌐 --> Opening Chrome to search Amazon for: {query}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            print("🌐 Opening Chrome and navigating to Amazon.in...")
            page.goto("https://www.amazon.in", timeout=60000)
            page.wait_for_timeout(2000)
            
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
            
            # Extract the actual product URLs bound directly to their text
            products_data = []
            try:
                products_data = page.evaluate('''() => {
                    let items = Array.from(document.querySelectorAll('div[data-asin]:not([data-asin=""])'));
                    let unique = [];
                    let seenUrls = new Set();
                    
                    for (let item of items) {
                        let a = item.querySelector('a[href*="/dp/"]');
                        if (a && a.href) {
                            let cleanUrl = a.href.split('?')[0]; // Remove tracking garbage
                            let text = item.innerText.trim().replace(/\\n+/g, ' ');
                            if (!seenUrls.has(cleanUrl) && text.length > 30) {
                                seenUrls.add(cleanUrl);
                                unique.push({url: cleanUrl, text: text});
                            }
                        }
                    }
                    return unique.slice(0, 5);
                }''')
            except Exception as e:
                print(f"Error extracting data: {e}")
                
            # VISUAL HACKATHON FEATURE: Go to the product page, scroll, and come back!
            for p_data in products_data:
                url = p_data['url']
                print(f"👀 Visually inspecting product: {url.split('/dp/')[0].split('/')[-1][:20]}...")
                try:
                    page.goto(url, timeout=20000)
                    page.wait_for_timeout(2000)
                    page.evaluate("window.scrollBy(0, 800)") # Scroll down
                    page.wait_for_timeout(2000) # Wait at the bottom
                    page.go_back(timeout=20000) # COME BACK!
                    page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"[VISUAL_HACK] Skipped visual reading: {e}")
            
            # Return the EXACT links bound to their text
            formatted_blocks = []
            for idx, p in enumerate(products_data):
                formatted_blocks.append(f"--- PRODUCT {idx+1} ---\nURL: {p['url']}\nDETAILS: {p['text']}")
            
            final_text = "\n\n".join(formatted_blocks)
            return f"--- EXACT RAW AMAZON DATA WITH URLS ---\n{final_text[:25000]}"
        except Exception as e:
            print(f"[PLAYWRIGHT ERROR] {e}")
            import traceback
            traceback.print_exc()
            return ""
        finally:
            browser.close()

def _run_playwright_google_sync(queries: List[str]) -> dict:
    """Runs a hardcoded Playwright scraper to search Google for fact-checking."""
    from playwright.sync_api import sync_playwright
    import urllib.parse
    
    print(f"\n🌐 --> Opening Chrome to fact-check {len(queries)} claims on Google...")
    results_map = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            for q in queries:
                print(f"   🔍 Fact-checking: {q}")
                # Use DuckDuckGo's pure HTML endpoint without interacting to bypass bot-detection loops
                url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
                page.goto(url, timeout=60000)
                
                page.wait_for_timeout(2000)
                
                # VISUAL HACKATHON FEATURE: Smoothly scroll through results (NO CLICKING)
                print("👀 Visually reading DuckDuckGo Search results...")
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(1500)
                
                text = page.evaluate("document.body.innerText")
                results_map[q] = text
            return results_map
        except Exception as e:
            print(f"[PLAYWRIGHT ERROR] {e}")
            import traceback
            traceback.print_exc()
            return results_map
        finally:
            browser.close()

# ── Agent 2: Search (Playwright + LLM Extraction) ─────────────────────────────
async def search_node(state: AgentState):
    """Uses Playwright to get raw Amazon text, then uses the LLM to extract the top 5 phones."""
    import concurrent.futures
    
    search_query = ""
    for msg in reversed(state["messages"]):
        if type(msg).__name__ == "HumanMessage" or msg.type == "human":
            search_query = extract_text(msg.content)
            break
            
    if not search_query:
        search_query = "Smartphones"

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        raw_amazon_text = await loop.run_in_executor(
            executor, _run_playwright_search_sync, search_query
        )

    if not raw_amazon_text or len(raw_amazon_text) < 100:
        print("❌ Playwright scraper failed or returned empty.")
        search_results_text = ""
    else:
        print(f"✅ Playwright extraction successful. Sending raw data to LLM for parsing...")
        print(f"\n[DEBUG] RAW AMAZON TEXT:\n{raw_amazon_text}\n")
        # Now ask the LLM to extract the 5 best phones from this raw text
        extraction_prompt = f"""You are a master data extractor. The user searched for: '{search_query}'.
Below is the raw, messy text scraped directly from the Amazon India search results page.

Extract exactly the top 5 smartphones from this text that BEST MATCH the user's requirements (Budget, Brand, etc.). 
CRITICAL RULE: Do not output more than 5 phones to keep the processing fast.

For the URL, you MUST extract the exact URL provided next to the product details. Every phone you list MUST have a valid, extracted URL. Do not omit the URL!

Return ONLY a numbered list separated by pipes. Example exactly like this:
1. Samsung Galaxy M15 5G | ₹12,000 | 4GB RAM, 128GB Storage | https://www.amazon.in/dp/B0CX...
2. Name | Price | Specs | URL

Do not write any conversational text.

Raw Amazon Text:
{raw_amazon_text[:25000]}
"""
        response = await llm.ainvoke([HumanMessage(content=extraction_prompt)])
        search_results_text = extract_text(response.content)
        print(f"✅ LLM extracted the following phones:\n{search_results_text[:300]}...")

    if not search_results_text or len(search_results_text) < 50:
        print("[SEARCH] Autonomous browser failed entirely — using LLM knowledge fallback")
        chat_history = "\n".join([f"{type(m).__name__}: {extract_text(m.content)}" for m in state["messages"]])
        fallback_prompt = f"""The user wants to buy a smartphone based on this conversation:
{chat_history}

List 5 real Samsung 5G smartphones available on Amazon.in.
For each phone use this exact format on ONE line:
1. Name | Price | Specs (RAM, battery, processor, camera) | https://amazon.in/s?k=encoded+search

IMPORTANT: Do NOT use markdown (like **bold**). Do NOT add any introductory text. Just output the 5 lines."""
        fallback_response = await llm.ainvoke([HumanMessage(content=fallback_prompt)])
        search_results_text = extract_text(fallback_response.content)

    # Parse the raw results (whether scraped or LLM fallback) into structured PhoneCandidates
    parse_prompt = f"""Here are raw search results for smartphones:
{search_results_text}

Extract ALL smartphones present in this text.
Reply ONLY with a list in this exact format (one phone per line, separated by the pipe | character):
Name | Price | Specs/Rating | URL

IMPORTANT: Do NOT use markdown (like **). Do NOT add introductory text. If there are fewer than 5 phones, extract what you can."""
    parse_response = await llm.ainvoke([HumanMessage(content=parse_prompt)])
    parsed_text = extract_text(parse_response.content)
    print(f"\n[SEARCH PARSER] Raw LLM Output:\n{parsed_text}\n")
    
    phones: List[PhoneCandidate] = []
    import re
    for line in parsed_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Safely strip leading numbers like "1." or "1)"
        line = re.sub(r'^\d+[\.\)]\s*', '', line)
            
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            phones.append(PhoneCandidate(
                name=parts[0],
                price=parts[1] if len(parts) > 1 else "N/A",
                specs=parts[2] if len(parts) > 2 else "N/A",
                url=parts[3] if len(parts) > 3 else "N/A",
            ))
        elif "₹" in line and len(line) > 10:
            # Fallback if the AI forgot the pipe characters but included a price
            phones.append(PhoneCandidate(
                name=line[:50].strip() + "...",
                price="See details",
                specs="Data extracted directly from AI text",
                url="N/A"
            ))

    print(f"[SEARCH] Final phones parsed: {len(phones)}")
    return {"search_results": phones, "current_phase": "comparison"}


# ── Agent 3: Comparison / Summarizer ──────────────────────────────────────────
async def comparison_node(state: AgentState):
    """Compares the 5 phones and highlights trade-offs."""
    phones = state.get("search_results", [])
    if not phones:
        return {
            "messages": [AIMessage(content="I couldn't find phones matching your criteria. Let's try again — what's your budget?")],
            "current_phase": "clarification",
        }

    # Build phones text WITH real links
    phones_text = "\n".join([
        f"{i+1}. **{p.name}** — {p.price}\n   Specs: {p.specs}\n   Link: {p.url}"
        for i, p in enumerate(phones)
    ])

    prompt = f"""You are the Comparison Agent. Compare these phones found on Amazon for the user:

{phones_text}

Provide a clear, plain-language breakdown of what differs between them (trade-offs in RAM, battery, camera, etc.).
After the comparison, show the numbered list with the Amazon links so the user can click them directly.
End by asking the user to reply with a number (1-{len(phones)}) to fact-check that listing's claims."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    text = extract_text(response.content)

    # Append the product links clearly at the end
    links_section = "\n\n---\n**Amazon Links:**\n" + "\n".join([
        f"{i+1}. [{p.name}]({p.url}) — {p.price}"
        for i, p in enumerate(phones)
    ])
    full_text = text + links_section

    return {
        "messages": [AIMessage(content=full_text)],
        "comparison_summary": full_text,
        "current_phase": "selection",
    }


# ── Selection handler (not a graph node, called from main.py) ─────────────────
async def selection_wait_node(state: AgentState):
    """Parses the user's phone selection."""
    last_msg = extract_text(state["messages"][-1].content)
    try:
        digits = [s for s in last_msg.split() if s.isdigit()]
        if digits:
            selection = int(digits[0]) - 1
            if 0 <= selection < len(state.get("search_results", [])):
                return {"selected_phone_index": selection, "current_phase": "verification"}
    except Exception:
        pass
    return {
        "messages": [AIMessage(content="Please reply with the number (1-5) of the phone you want me to fact-check.")],
        "current_phase": "selection",
    }


def _run_amazon_product_sync(url: str) -> str:
    """Visits the Amazon product page to extract full specs before fact-checking."""
    from playwright.sync_api import sync_playwright
    print(f"\n🌐 --> Opening Chrome to read FULL specs directly from Amazon product page...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(2000)
            # Extract ONLY the core product details, ignoring related products and reviews
            product_details = page.evaluate('''() => {
                let title = document.querySelector('#productTitle') ? document.querySelector('#productTitle').innerText.trim() : '';
                let bullets = document.querySelector('#feature-bullets') ? document.querySelector('#feature-bullets').innerText.trim() : '';
                let specs1 = document.querySelector('#productDetails_techSpec_section_1') ? document.querySelector('#productDetails_techSpec_section_1').innerText.trim() : '';
                let specs2 = document.querySelector('#productDetails_techSpec_section_2') ? document.querySelector('#productDetails_techSpec_section_2').innerText.trim() : '';
                let description = document.querySelector('#productDescription') ? document.querySelector('#productDescription').innerText.trim() : '';
                return `Title: ${title}\\n\\nKey Features:\\n${bullets}\\n\\nTechnical Specifications:\\n${specs1}\\n${specs2}\\n\\nDescription:\\n${description}`;
            }''')
            return product_details
        except Exception as e:
            return ""
        finally:
            browser.close()

# ── Agent 4: Verification Planner ─────────────────────────────────────────────
async def verification_planner_node(state: AgentState):
    """Decomposes the listing into specific checkable claims."""
    import concurrent.futures
    import asyncio
    
    phone = state["search_results"][state["selected_phone_index"]]

    # Run Playwright in a thread to scrape the full Amazon product page!
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        full_amazon_text = await loop.run_in_executor(
            executor, _run_amazon_product_sync, phone.url
        )
    
    if full_amazon_text and len(full_amazon_text) > 100:
        phone_specs_context = full_amazon_text[:15000]
    else:
        phone_specs_context = phone.specs

    prompt = f"""You are the Verification Planner. The user wants to fact-check this phone listing:
Name: {phone.name}
URL: {phone.url}
Full Product Details: {phone_specs_context}

List 3-4 specific checkable claims extracted STRICTLY from this listing's specs. Do not invent claims.
Focus on claims that are often exaggerated in marketing (e.g., Battery capacity, RAM size, Processor model).

Reply ONLY as a numbered list, one claim per line. Example:
1. [Insert Claim 1 from specs]
2. [Insert Claim 2 from specs]
3. [Insert Claim 3 from specs]
4. [Insert Claim 4 from specs]"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = extract_text(response.content)
        claims = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Strip leading number/bullet
            if line[0].isdigit():
                line = line.split(".", 1)[-1].strip()
            elif line.startswith("-"):
                line = line[1:].strip()
            if line:
                claims.append(VerificationClaim(claim=line, context=phone.specs))
        if not claims:
            claims = [VerificationClaim(claim="RAM amount", context=phone.specs)]
    except Exception as e:
        print(f"[PLANNER] Claims extraction failed: {e}")
        claims = [VerificationClaim(claim="RAM amount", context=phone.specs)]

    print(f"[PLANNER] Extracted {len(claims)} claims to verify")
    return {
        "claims_to_check": claims,
        "current_phase": "verification_execution",
    }


# ── Agent 5: Verifier ─────────────────────────────────────────────────────────
async def verifier_node(state: AgentState):
    """Independently verifies each claim via browser search."""
    import concurrent.futures
    claims = state.get("claims_to_check", [])
    phone = state["search_results"][state["selected_phone_index"]]

    # Create all queries first
    queries = [f"{phone.name} {claim.claim} specs review" for claim in claims]
    
    # Run them all sequentially in ONE browser window
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        raw_results = await loop.run_in_executor(
            executor, _run_playwright_google_sync, queries
        )

    results = []
    for claim in claims:
        query = f"{phone.name} {claim.claim} specs review"
        raw_text = raw_results.get(query, "")
            
        if not raw_text or len(raw_text) < 100:
            print(f"❌ Verifier Playwright failed for '{claim.claim}'")
            findings = f"Could not independently verify '{claim.claim}'. Marking as potentially misleading."
        else:
            findings = raw_text[:15000]

        try:
            verdict_prompt = f"""Based on these search results, is the claim '{claim.claim}' genuine or misleading?

Search Results:
{findings}

IMPORTANT RULE: If the search results generally confirm the claim (e.g. they mention the phone has 128GB storage), you MUST say it is verified. Do not be overly skeptical or guess that it might be a lower model unless the text explicitly says so.

Reply in exactly this format (two lines only):
VERDICT: true   (or false)
EXPLANATION: <one sentence explaining why>"""
            verdict_response = await llm.ainvoke([HumanMessage(content=verdict_prompt)])
            verdict_text = extract_text(verdict_response.content).strip()
            is_verified = False
            explanation = verdict_text
            for line in verdict_text.split("\n"):
                if line.upper().startswith("VERDICT:"):
                    is_verified = "true" in line.lower()
                elif line.upper().startswith("EXPLANATION:"):
                    explanation = line.split(":", 1)[-1].strip()
            results.append(VerificationResult(
                claim=claim.claim,
                is_verified=is_verified,
                explanation=explanation,
            ))
        except Exception as e:
            print(f"[VERIFIER] Verdict extraction failed: {e}")
            results.append(VerificationResult(
                claim=claim.claim,
                is_verified=False,
                explanation=f"Verification inconclusive: {str(e)}",
            ))

    return {"verification_results": results}


# ── Agent 6: Critic / Risk Synthesis ──────────────────────────────────────────
async def critic_node(state: AgentState):
    """Synthesizes verification results looking for compounding red flags."""
    results = state.get("verification_results", [])

    prompt = "You are the Critic Agent. Review these verification results for a phone listing:\n\n"
    for r in results:
        status = "✅ Verified" if r.is_verified else "⚠️ Potentially Misleading"
        prompt += f"- Claim: {r.claim} | {status} | {r.explanation}\n"

    prompt += "\nSynthesize these findings. Look for compounding red flags. Provide a harsh, honest risk synthesis."

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    text = extract_text(response.content)
    return {"critic_synthesis": text}


# ── Agent 7: Finalizer ────────────────────────────────────────────────────────
async def finalizer_node(state: AgentState):
    """Assembles the final plain-language report."""
    phone = state["search_results"][state["selected_phone_index"]]
    critic_synth = state.get("critic_synthesis", "")
    results = state.get("verification_results", [])

    results_text = "\n".join([
        f"- {r.claim}: {'✅ Verified' if r.is_verified else '⚠️ Misleading'} — {r.explanation}"
        for r in results
    ])

    prompt = f"""You are the Finalizer Agent. Write the final report for the user in plain, non-technical language.

Phone: {phone.name} — {phone.price}
Specs: {phone.specs}

Individual Verification Results:
{results_text}

Critic Risk Synthesis:
{critic_synth}

Write a clear, honest summary:
1. Which claims are genuine
2. Which claims are misleading (explain WHY in simple terms)
3. Your final recommendation: Buy, Proceed with Caution, or Avoid"""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    text = extract_text(response.content)

    return {
        "messages": [AIMessage(content=text)],
        "final_report": text,
        "current_phase": "selection",
    }


# ── Graph Construction ─────────────────────────────────────────────────────────
workflow = StateGraph(AgentState)

workflow.add_node("conversation_node", conversation_node)
workflow.add_node("search_node", search_node)
workflow.add_node("comparison_node", comparison_node)
workflow.add_node("selection_wait_node", selection_wait_node)
workflow.add_node("verification_planner_node", verification_planner_node)
workflow.add_node("verifier_node", verifier_node)
workflow.add_node("critic_node", critic_node)
workflow.add_node("finalizer_node", finalizer_node)


def route_clarification(state: AgentState):
    if state.get("ready_to_search"):
        return "search_node"
    return END


def route_selection(state: AgentState):
    if state.get("selected_phone_index") is not None:
        return "verification_planner_node"
    return END


workflow.set_entry_point("conversation_node")
workflow.add_conditional_edges("conversation_node", route_clarification, {"search_node": "search_node", END: END})
workflow.add_edge("search_node", "comparison_node")
workflow.add_edge("comparison_node", END)

workflow.add_conditional_edges("selection_wait_node", route_selection, {"verification_planner_node": "verification_planner_node", END: END})
workflow.add_edge("verification_planner_node", "verifier_node")
workflow.add_edge("verifier_node", "critic_node")
workflow.add_edge("critic_node", "finalizer_node")
workflow.add_edge("finalizer_node", END)

app = workflow.compile()
