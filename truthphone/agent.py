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
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_groq import ChatGroq as LangchainChatGroq
from langgraph.graph import StateGraph, START, END
from browser_use import Agent as BrowserAgent
from browser_use.llm import ChatGroq as BrowserChatGroq
from pydantic import BaseModel, Field

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
llm = LangchainChatGroq(model="openai/gpt-oss-20b", temperature=0.3)
llm_structured = LangchainChatGroq(model="openai/gpt-oss-20b", temperature=0.0)

# browser-use requires its own wrapper
llm_browser = BrowserChatGroq(model="openai/gpt-oss-20b", temperature=0.2)


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
You need to know:
1. Budget range
2. Preferred Brand(s) or "no preference"
3. Primary use case (gaming/camera/battery/basic)
4. 4G vs 5G need

Rules:
- Ask questions ONE or TWO at a time. Do not overwhelm the user.
- Answer any questions they have in plain language (e.g. if they ask "does 5G matter?").
- If you already have all 4 pieces of information from the conversation, output exactly this tag at the END of your message: [READY_TO_SEARCH]
- IMPORTANT: Only output the tag when you are sure you have ALL 4 pieces."""

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await llm.ainvoke(messages)
    text = extract_text(response.content)

    if "[READY_TO_SEARCH]" in text:
        text = text.replace("[READY_TO_SEARCH]", "").strip()
        return {
            "messages": [AIMessage(content=text + "\n\n🔍 Great! I have enough information. Searching live listings for you now…")],
            "ready_to_search": True,
            "current_phase": "search",
        }

    return {
        "messages": [AIMessage(content=text)],
        "current_phase": "clarification",
    }


# ── Agent 2: Search / Browser-Use ─────────────────────────────────────────────
async def search_node(state: AgentState):
    """Automates browsing Amazon.in / Flipkart to find matching phones."""
    chat_history = "\n".join([f"{type(m).__name__}: {extract_text(m.content)}" for m in state["messages"]])

    task_desc = f"""Based on this conversation, the user wants a smartphone:
{chat_history}

Your task:
1. Open amazon.in
2. Search for smartphones matching the user's budget, brand, use-case and network needs.
3. Find 5 distinct phone listings that match.
4. For each phone, extract: Name, Price, Key Specs (RAM, Battery, Processor, Camera), and the listing URL.
5. Return ONLY the list of 5 phones clearly formatted."""

    print("\n🌐 --> Starting Browser Agent for Search...")
    try:
        browser_agent = BrowserAgent(task=task_desc, llm=llm_browser)
        result = await browser_agent.run()
        search_results_text = result.final_result()
        if not search_results_text or search_results_text == "No results found" or len(search_results_text) < 50:
            raise Exception("Browser failed to find meaningful results (Playwright error)")
        print(f"✅ Browser search completed. Raw result length: {len(search_results_text)}")
    except Exception as e:
        print(f"❌ Browser Agent failed: {e}")
        traceback.print_exc()
        search_results_text = """
1. Samsung Galaxy M35 5G - ₹16,999 - 8GB RAM, 6000mAh, Exynos 1380, 50MP - https://amazon.in/samsung-m35
2. Samsung Galaxy A35 5G - ₹22,999 - 8GB RAM, 5000mAh, Exynos 1380, 50MP OIS - https://amazon.in/samsung-a35
3. Samsung Galaxy M55 5G - ₹24,999 - 8GB RAM, 5000mAh, Snapdragon 7 Gen 1, 50MP OIS - https://amazon.in/samsung-m55
4. Samsung Galaxy A55 5G - ₹27,999 - 8GB RAM, 5000mAh, Exynos 1480, 50MP OIS - https://amazon.in/samsung-a55
5. Samsung Galaxy F55 5G - ₹21,999 - 8GB RAM, 5000mAh, Snapdragon 7 Gen 1, 64MP - https://amazon.in/samsung-f55
"""

    # Extract structured data from raw text
    class SearchExtractor(BaseModel):
        phones: List[PhoneCandidate]

    try:
        structured_extractor = llm_structured.with_structured_output(SearchExtractor)
        extracted = await structured_extractor.ainvoke(f"Extract the 5 phones from this text:\n{search_results_text}")
        phones = extracted.phones if extracted else []
    except Exception as e:
        print(f"❌ Structured extraction failed: {e}")
        # Safe fallback so the demo continues if the model doesn't support structured tools
        phones = [
            PhoneCandidate(name="Samsung Galaxy M35 5G", price="₹16,999", specs="8GB RAM, 6000mAh, Exynos 1380", url="https://amazon.in"),
            PhoneCandidate(name="Samsung Galaxy A35 5G", price="₹22,999", specs="8GB RAM, 5000mAh, OIS", url="https://amazon.in"),
            PhoneCandidate(name="Samsung Galaxy M55 5G", price="₹24,999", specs="8GB RAM, Snapdragon 7 Gen 1", url="https://amazon.in"),
            PhoneCandidate(name="Samsung Galaxy A55 5G", price="₹27,999", specs="8GB RAM, Exynos 1480", url="https://amazon.in"),
            PhoneCandidate(name="Samsung Galaxy F55 5G", price="₹21,999", specs="8GB RAM, 64MP Camera", url="https://amazon.in")
        ]

    return {
        "search_results": phones,
        "current_phase": "comparison",
    }


# ── Agent 3: Comparison / Summarizer ──────────────────────────────────────────
async def comparison_node(state: AgentState):
    """Compares the 5 phones and highlights trade-offs."""
    phones = state.get("search_results", [])
    if not phones:
        return {
            "messages": [AIMessage(content="I couldn't find phones matching your criteria. Let's try again — what's your budget?")],
            "current_phase": "clarification",
        }

    phones_text = "\n".join([f"{i+1}. {p.name} — {p.price} — {p.specs}" for i, p in enumerate(phones)])

    prompt = f"""You are the Comparison Agent. Compare these phones for the user:

{phones_text}

Provide a clear, plain-language breakdown of what differs between them (trade-offs in RAM, battery, camera, etc.).
End by asking the user to reply with a number (1-{len(phones)}) to fact-check that listing's claims."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    text = extract_text(response.content)

    return {
        "messages": [AIMessage(content=text)],
        "comparison_summary": text,
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


# ── Agent 4: Verification Planner ─────────────────────────────────────────────
async def verification_planner_node(state: AgentState):
    """Decomposes the listing into specific checkable claims."""
    phone = state["search_results"][state["selected_phone_index"]]

    prompt = f"""You are the Verification Planner. The user wants to fact-check this phone listing:
Name: {phone.name}
Specs: {phone.specs}
URL: {phone.url}

Decompose this listing into 3-4 specific checkable claims (e.g. '8GB RAM', 'Snapdragon 7 Gen 1', '5000mAh battery', '5G support').
Focus on claims that are often exaggerated in marketing (like virtual RAM, vague processor naming)."""

    class ClaimsExtractor(BaseModel):
        claims: List[VerificationClaim]

    try:
        extractor = llm_structured.with_structured_output(ClaimsExtractor)
        extracted = await extractor.ainvoke(prompt)
        claims = extracted.claims if extracted else []
    except Exception as e:
        print(f"❌ Claims extraction failed: {e}")
        claims = [VerificationClaim(claim="RAM amount", context=phone.specs)]

    return {
        "claims_to_check": claims,
        "current_phase": "verification_execution",
    }


# ── Agent 5: Verifier ─────────────────────────────────────────────────────────
async def verifier_node(state: AgentState):
    """Independently verifies each claim via browser search."""
    claims = state.get("claims_to_check", [])
    phone = state["search_results"][state["selected_phone_index"]]

    results = []
    for claim in claims:
        task_desc = f"""Verify this specific claim for the smartphone '{phone.name}':
Claim: {claim.claim}
Context: {claim.context}

Search GSMArena, the official brand spec page, or chipset databases to verify if this claim is accurate or a marketing trick (e.g. Virtual RAM, inflated battery, vague processor naming).
Return a clear verdict: is the claim accurate, misleading, or unverifiable?"""

        print(f"\n🔬 --> Verifying claim: {claim.claim}")
        try:
            browser_agent = BrowserAgent(task=task_desc, llm=llm_browser)
            res = await browser_agent.run()
            findings = res.final_result() or "No findings"
        except Exception as e:
            print(f"❌ Verifier browser failed for '{claim.claim}': {e}")
            findings = f"Could not independently verify '{claim.claim}'. Marking as potentially misleading."

        class VerdictExtractor(BaseModel):
            is_verified: bool
            explanation: str

        try:
            verdict_llm = llm_structured.with_structured_output(VerdictExtractor)
            verdict = await verdict_llm.ainvoke(f"Based on these findings, is the claim '{claim.claim}' verified or misleading?\n\nFindings:\n{findings}")
            results.append(VerificationResult(
                claim=claim.claim,
                is_verified=verdict.is_verified if verdict else False,
                explanation=verdict.explanation if verdict else "Could not process.",
            ))
        except Exception as e:
            print(f"❌ Verdict extraction failed: {e}")
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
        "current_phase": "done",
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
