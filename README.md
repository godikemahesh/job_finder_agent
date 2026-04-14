# 🤖 WhatsApp AI Job Agent

A WhatsApp-based AI assistant that helps users find jobs matching their resume — powered by **FastAPI**, **Twilio**, and **Adzuna**.

Users interact entirely through WhatsApp to register, paste their resume, extract structured data (skills, role, experience), and receive personalized job recommendations.

---

## ✨ Features

- **WhatsApp-first**: Entire workflow happens via WhatsApp messages
- **Resume Parsing**: Extracts skills, role, experience, and location (LLM + rule-based fallback)
- **Job Search**: Fetches real jobs from Adzuna API, ranked against your profile
- **Multi-user**: Each WhatsApp number is a unique user with their own profile
- **Background Processing**: Long-running job searches happen in the background
- **State Machine**: Guided registration flow with conversation state tracking

---

## 📁 Project Structure

```
job_agent/
├── main.py            # FastAPI app — webhook + command routing
├── db.py              # SQLite database — user CRUD + state management
├── agent.py           # Resume parsing + job search + formatting
├── twilio_utils.py    # Twilio WhatsApp message sender
├── config.py          # All settings (env vars with defaults)
├── matcher.py         # Job ranking engine (keyword + semantic scoring)
├── job_fetcher.py     # Adzuna API client + CSV fallback
├── requirements.txt   # Python dependencies
└── adzuna_jobs.csv    # Fallback job data (used when API is unavailable)
```

---

## 📱 WhatsApp Commands

| Command | Description |
|---------|-------------|
| `/new` | Register as a new user |
| `/profile` | View your extracted profile |
| `/update` | Update your resume |
| `search job for me` | Find jobs matching your profile |
| `/help` | Show available commands |
| `hi` / `hello` | Show help message |

---

## ⚙️ Setup

### 1. Clone & Install

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env` file or set these variables in your terminal:

```bash
# REQUIRED — Twilio WhatsApp credentials
set TWILIO_ACCOUNT_SID=your_twilio_account_sid
set TWILIO_AUTH_TOKEN=your_twilio_auth_token
set TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# REQUIRED — Adzuna job search API
set ADZUNA_APP_ID=your_adzuna_app_id
set ADZUNA_APP_KEY=your_adzuna_app_key

# OPTIONAL — Groq LLM for smarter resume parsing
set GROQ_API_KEY=your_groq_api_key

# OPTIONAL — Customization
set ADZUNA_COUNTRY_CODE=in
set JOB_ROLE_QUERY=AI ML Engineer
set TOP_JOBS_TO_RETURN=5
set MINIMUM_SCORE=0.15
```

### 3. Set Up Twilio WhatsApp Sandbox

1. Go to [Twilio Console](https://console.twilio.com/)
2. Navigate to **Messaging** → **Try it Out** → **Send a WhatsApp message**
3. Follow the instructions to join your sandbox (send the join code from your phone)
4. Set the webhook URL for **"When a message comes in"**:
   ```
   https://your-server.com/whatsapp
   ```
   Method: `POST`

### 4. Run Locally

```bash
# Start the FastAPI server
uvicorn main:app --reload --port 8000

# Or run directly
python main.py
```

The server will start at `http://localhost:8000`.

### 5. Expose Local Server (for Twilio webhook)

Twilio needs a public URL to send webhooks. Use **ngrok**:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL and set it as your Twilio webhook:
```
https://xxxx.ngrok.io/whatsapp
```

---

## 🚀 Deploy on HuggingFace Spaces

### Step 1: Create a Space

1. Go to [HuggingFace Spaces](https://huggingface.co/spaces)
2. Click **"Create new Space"**
3. Choose **Docker** as the SDK
4. Name it (e.g., `whatsapp-job-agent`)

### Step 2: Create a Dockerfile

Create a `Dockerfile` in your project root:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
```

### Step 3: Set Secrets

In your HuggingFace Space settings, add these secrets:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`
- `GROQ_API_KEY` (optional)

### Step 4: Push and Deploy

```bash
git init
git remote add space https://huggingface.co/spaces/YOUR_USERNAME/whatsapp-job-agent
git add .
git commit -m "Deploy WhatsApp AI Job Agent"
git push space main
```

### Step 5: Update Twilio Webhook

Set your Twilio webhook URL to:
```
https://YOUR_USERNAME-whatsapp-job-agent.hf.space/whatsapp
```

---

## 🔄 User Flow

```
User sends /new
    ↓
Bot asks: "What is your name?"
    ↓
User sends name (e.g., "Mahesh")
    ↓
Bot asks: "Paste your resume text"
    ↓
User pastes resume
    ↓
Bot parses resume → extracts skills, role, experience
Bot confirms: "Profile saved! ✅"
    ↓
User sends "search job for me"
    ↓
Bot: "🔍 Searching..." (immediate)
Bot: sends job results (background task)
```

---

## 🧪 Testing with curl

You can test the webhook locally without WhatsApp:

```bash
# Test /new command
curl -X POST http://localhost:8000/whatsapp \
  -d "Body=/new" \
  -d "From=whatsapp:+919876543210"

# Test sending a name
curl -X POST http://localhost:8000/whatsapp \
  -d "Body=Mahesh" \
  -d "From=whatsapp:+919876543210"

# Test the health check
curl http://localhost:8000/
```

---

## 📝 Notes

- **SQLite** is used for the MVP. For production, consider PostgreSQL.
- **sentence-transformers** is optional — the matcher falls back to lexical overlap if unavailable.
- **Groq LLM** is optional — resume parsing falls back to rule-based extraction.
- The Adzuna fallback CSV (`adzuna_jobs.csv`) is used when the live API is unavailable.
- WhatsApp messages are automatically split if they exceed the character limit.

---

## 📄 License

MIT
