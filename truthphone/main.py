import os
import traceback
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel
from typing import List, Optional
import copy

import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from agent import app as langgraph_app, extract_text, selection_wait_node

app = FastAPI(title="TruthPhone API")


def make_fresh_state():
    return {
        "messages": [],
        "requirements": {},
        "ready_to_search": False,
        "search_results": [],
        "comparison_summary": "",
        "selected_phone_index": None,
        "claims_to_check": [],
        "verification_results": [],
        "critic_synthesis": "",
        "final_report": "",
        "current_phase": "clarification",
    }


global_state = make_fresh_state()


class ChatRequest(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TruthPhone — Smart Phone Fact-Checker</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            padding: 20px;
        }
        .container { width: 100%; max-width: 860px; }
        header {
            text-align: center;
            padding: 24px 0 16px;
        }
        header h1 {
            font-size: 2rem;
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        header p { color: #94a3b8; font-size: 0.9rem; margin-top: 4px; }
        #chatbox {
            height: 520px;
            overflow-y: auto;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 12px;
            scroll-behavior: smooth;
        }
        .msg {
            margin-bottom: 16px;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.6;
            font-size: 0.95rem;
            max-width: 85%;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .user {
            background: linear-gradient(135deg, #1d4ed8, #3b82f6);
            color: #fff;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }
        .bot {
            background: #334155;
            color: #e2e8f0;
            border-bottom-left-radius: 4px;
            white-space: pre-wrap;
        }
        .bot strong { color: #38bdf8; }
        .input-row {
            display: flex;
            gap: 8px;
        }
        #userInput {
            flex: 1;
            padding: 14px 16px;
            border-radius: 10px;
            border: 1px solid #334155;
            background: #1e293b;
            color: #e2e8f0;
            font-size: 1rem;
            outline: none;
            transition: border 0.2s;
        }
        #userInput:focus { border-color: #3b82f6; }
        .btn {
            padding: 14px 24px;
            border-radius: 10px;
            border: none;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, opacity 0.2s;
        }
        .btn:active { transform: scale(0.96); }
        .btn-send { background: linear-gradient(135deg, #3b82f6, #6366f1); color: #fff; }
        .btn-send:hover { opacity: 0.9; }
        .btn-send:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-reset { background: #dc2626; color: #fff; }
        .btn-reset:hover { opacity: 0.9; }
        .typing {
            display: none;
            padding: 12px 16px;
            color: #94a3b8;
            font-style: italic;
        }
        .typing.active { display: block; }
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>📱 TruthPhone</h1>
        <p>Guided Smartphone Buying + Fact-Check Assistant &mdash; 7 AI Agents</p>
    </header>
    <div id="chatbox">
        <div class="msg bot"><strong>TruthPhone:</strong><br/>Hi! I'm TruthPhone. Tell me what kind of smartphone you're looking for, and I'll help you find the best one — then fact-check the listing before you buy.</div>
    </div>
    <div class="typing" id="typing">🤖 Agents are working…</div>
    <div class="input-row">
        <input type="text" id="userInput" placeholder="I want to buy a smartphone..." autocomplete="off">
        <button class="btn btn-send" id="sendBtn" onclick="sendMessage()">Send</button>
        <button class="btn btn-reset" onclick="resetChat()">Reset</button>
    </div>
</div>
<script>
    const chatbox = document.getElementById('chatbox');
    const input = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const typing = document.getElementById('typing');

    input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });

    function appendMessage(sender, text, cls) {
        const div = document.createElement('div');
        div.className = 'msg ' + cls;
        div.innerHTML = '<strong>' + sender + ':</strong><br/>' + text;
        chatbox.appendChild(div);
        chatbox.scrollTop = chatbox.scrollHeight;
    }

    async function sendMessage() {
        const msg = input.value.trim();
        if (!msg) return;

        appendMessage('You', msg, 'user');
        input.value = '';
        sendBtn.disabled = true;
        typing.classList.add('active');

        try {
            const resp = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            const data = await resp.json();
            if (data.response) {
                appendMessage('TruthPhone', data.response, 'bot');
            } else if (data.error) {
                appendMessage('⚠️ Error', data.error, 'bot');
            }
        } catch (err) {
            appendMessage('⚠️ Error', 'Network error: ' + err.message, 'bot');
        } finally {
            sendBtn.disabled = false;
            typing.classList.remove('active');
        }
    }

    async function resetChat() {
        await fetch('/reset', { method: 'POST' });
        chatbox.innerHTML = '<div class="msg bot"><strong>TruthPhone:</strong><br/>Hi! I\\'m TruthPhone. Tell me what kind of smartphone you\\'re looking for, and I\\'ll help you find the best one — then fact-check the listing before you buy.</div>';
    }
</script>
</body>
</html>"""


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    global global_state

    try:
        global_state["messages"].append(HumanMessage(content=req.message))

        # ── Phase: Selection (user picking a phone number) ─────────────
        if global_state["current_phase"] == "selection":
            res = await selection_wait_node(global_state)

            # Merge returned keys into global state
            if "messages" in res:
                global_state["messages"].extend(res["messages"])
            if "selected_phone_index" in res:
                global_state["selected_phone_index"] = res["selected_phone_index"]
            if "current_phase" in res:
                global_state["current_phase"] = res["current_phase"]

            if global_state.get("selected_phone_index") is not None:
                # Run the verification pipeline (planner -> verifier -> critic -> finalizer)
                # We need to enter through selection_wait_node in the graph
                final_state = await langgraph_app.ainvoke(global_state)
                global_state.update(final_state)
                return {"response": _get_latest_ai_text(final_state)}
            else:
                return {"response": extract_text(res["messages"][-1].content) if res.get("messages") else "Please pick a number (1-5)."}

        # ── All other phases: run the main graph ───────────────────────
        final_state = await langgraph_app.ainvoke(global_state)
        global_state.update(final_state)

        # If we've reached comparison, return the comparison summary
        if final_state.get("current_phase") == "selection" and final_state.get("comparison_summary"):
            return {"response": final_state["comparison_summary"]}

        return {"response": _get_latest_ai_text(final_state)}

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=200,
            content={"response": f"⚠️ Something went wrong: {str(e)}. Please click Reset and try again."}
        )


def _get_latest_ai_text(state: dict) -> str:
    """Extract the latest AI message text from state."""
    for m in reversed(state.get("messages", [])):
        if isinstance(m, AIMessage):
            return extract_text(m.content)
    return "No response generated."


@app.post("/reset")
async def reset_endpoint():
    global global_state
    global_state = make_fresh_state()
    return {"status": "ok"}


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
