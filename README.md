# HackFusion 2026 - TruthPhone 📱🔍

**TruthPhone** is an AI-powered multi-agent shopping and verification platform built for **HackFusion 2026**. It combines interactive recommendation with real-time web verification to help users find the best smartphone and verify e-commerce listing claims before purchasing.

---

## 🌟 Key Features

- 💬 **Interactive Guided Buying**: Multi-step conversation agent to understand user requirements (budget, brand, features, usage).
- 🌐 **Real-time Web Searching & Extraction**: Uses `browser-use` to search Amazon and Flipkart for actual phone listings.
- 🔬 **Automated Claim Verification**: Extracts key marketing specs and fact-checks them against third-party reviews and official specs using automated web search.
- 🚨 **Risk & Red Flag Synthesis**: Summarizes trade-offs, potential dealbreakers, and verification confidence scores.
- ⚡ **Groq LLM Acceleration**: Powered by high-speed inference on Groq using `openai/gpt-oss-20b`.

---

## 🏗 Project Structure

```
hackfusion/
├── truthphone/
│   ├── main.py          # FastAPI application server & HTML UI
│   ├── agent.py         # LangGraph workflow & multi-agent definitions
│   ├── state.py         # Pydantic & LangGraph state models
│   └── README.md        # TruthPhone documentation
├── .gitignore
└── README.md
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Google Chrome installed

### 2. Environment Setup
```bash
# Navigate to truthphone
cd truthphone

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install langgraph langchain-core langchain-groq browser-use playwright fastapi uvicorn pydantic
playwright install
```

### 3. API Key Configuration
Set your Groq API key:
```bash
# Windows PowerShell:
$env:GROQ_API_KEY="gsk_your_groq_api_key"

# Linux/macOS:
export GROQ_API_KEY="gsk_your_groq_api_key"
```

### 4. Run the Application
```bash
python main.py
```

Open your browser and navigate to `http://localhost:8000`.

---

## 🤖 Agent Architecture

TruthPhone uses a 7-agent architecture orchestrated via **LangGraph**:

1. **Conversation / Clarification Agent**: Engages user and extracts search constraints.
2. **Search / Browser-Use Agent**: Dynamically navigates e-commerce sites to find matching products.
3. **Comparison & Summarizer Agent**: Evaluates options and selects top candidates.
4. **Verification Planner**: Extracts testable product claims (OIS, battery, processor, display).
5. **Verifier Agent**: Automates browser checks across review sites and benchmarks.
6. **Critic / Risk Synthesis Agent**: Evaluates accuracy and flags deceptive marketing.
7. **Finalizer Agent**: Compiles clear, actionable purchasing advice.

---

## 📜 License
MIT License
