# TruthPhone

TruthPhone is a multi-agent AI reasoning platform designed for a 1-day hackathon (HackFusion 2026). It serves as a Guided Smartphone Buying + Fact-Check Assistant.

## Agent Architecture
This project implements the 7 required distinct agents:
1. **Conversation/Clarification Agent**: Manages dialogue, asks questions one by one.
2. **Search/Browser-Use Agent**: Automates browsing (Amazon/Flipkart) using `browser-use` to find real candidate phones matching criteria.
3. **Comparison/Summarizer Agent**: Compares the top 5 phones and their trade-offs.
4. **Verification Planner**: Decomposes the listing into specific checkable claims.
5. **Verifier Agent**: Uses `browser-use` to independently verify claims (fact-checking).
6. **Critic/Risk-Synthesis Agent**: Analyzes verification results for compounding red flags.
7. **Finalizer**: Assembles the final non-technical report.

## Setup Instructions
1. Install dependencies:
```bash
pip install langgraph langchain langchain-google-genai browser-use playwright fastapi uvicorn pydantic
playwright install
```
2. Set your Google API Key:
```bash
$env:GEMINI_API_KEY="your_api_key_here"
```
3. Run the application:
```bash
python main.py
```
4. Access the UI at: `http://localhost:8000`
