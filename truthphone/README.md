<div align="center">
  <h1>📱 TruthPhone</h1>
  <p><strong>A Multi-Agent AI Smartphone Buying & Fact-Checking Assistant</strong></p>
  <p><em>Built for HackFusion 2026</em></p>
</div>

---

## 🛑 Problem Statement
E-commerce sites (like Amazon) are flooded with exaggerated marketing claims, fake specifications, and overwhelming choices. Consumers often buy smartphones based on misleading numbers (e.g., fake 120Hz refresh rates or exaggerated battery life) because they don't have the time to cross-reference independent tech blogs for the truth.

## 💡 Solution
TruthPhone is an AI-powered web application that not only helps users find the perfect phone based on their budget, but actively acts as a shield against marketing lies. Once a user selects a phone, TruthPhone autonomously scrapes the internet to independently fact-check the manufacturer's claims before the user clicks "Buy."

## ✨ Features
- **Conversational Guidance:** Natural language chat helps you figure out exactly what phone fits your needs.
- **Live Amazon Scraping:** Uses Playwright to physically navigate Amazon, bypass bot detection, and pull real-time pricing and specs.
- **Dynamic Comparisons:** Automatically generates beautiful Markdown comparison tables of the top 5 phones.
- **Independent Fact-Checking:** Cross-references marketing claims (e.g., "800 nits brightness") against independent tech blogs via DuckDuckGo.
- **Verdict Engine:** Delivers a final, plain-English "Buy" or "Don't Buy" recommendation highlighting any red flags.
- **Modern UI/UX:** Sleek, responsive, deep-blue glassmorphism frontend interface.

## 🛠️ Tech Stack
- **Backend:** Python, FastAPI
- **AI Orchestration:** LangGraph (Multi-Agent framework), LangChain
- **LLM Engine:** Groq (Llama-3 / Mixtral for blazing fast inference)
- **Web Automation:** Playwright (Synchronous Live Scraping)
- **Frontend:** HTML, CSS (Glassmorphism), JavaScript, Marked.js (Markdown parsing)

## 👥 Team Members
- **Nikhil Jaiswal** (GitHub: [@NikhilJaiswal-79](https://github.com/NikhilJaiswal-79))
- *(Add your teammates here!)*

## 🚀 Setup Instructions

### 1. Prerequisites
Ensure you have Python 3.10+ installed on your machine.

### 2. Installation
Clone the repository and set up a virtual environment:
```bash
git clone https://github.com/NikhilJaiswal-79/hackfusion.git
cd hackfusion/truthphone

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate   # For Windows

# Install dependencies
pip install langgraph langchain langchain-groq playwright fastapi uvicorn pydantic
playwright install
```

### 3. Environment Variables
You need a Groq API Key to run the language models. Create a `.env` file in the `truthphone` directory:
```env
GROQ_API_KEY="your_groq_api_key_here"
```

### 4. Running the Application
Start the FastAPI server:
```bash
python -m uvicorn main:app --reload
```
Open your browser and navigate to: `http://localhost:8000`

### 5. Running with Ngrok (Public Sharing)
To share your local application publicly (for hackathon presentations):
1. Download and authenticate [Ngrok](https://ngrok.com/).
2. Run your Uvicorn server in one terminal.
3. In a second terminal, run:
```bash
ngrok http 8000
```
4. Share the provided `https://...` Forwarding URL!
