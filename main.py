"""
main.py — FastAPI WhatsApp AI Job Agent.

This is the main entry point. It exposes:
  - GET  /          → health check
  - POST /whatsapp  → Twilio webhook for incoming WhatsApp messages

User Flow:
  1. User sends /new         → creates account, asks for name
  2. User sends their name   → saves name, asks for resume
  3. User pastes resume text  → parses resume, stores structured data
  4. User sends "search job"  → fetches + ranks jobs, returns results
  5. User sends /profile      → shows extracted profile info
  6. User sends /update       → lets them re-paste resume
  7. User sends /help         → shows available commands

Run locally:
  uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Form, Response
from twilio.twiml.messaging_response import MessagingResponse

from agent import format_job_summary, format_single_job_card, format_profile, parse_resume, search_jobs
from config import MAX_RESUME_LENGTH
from db import create_user, get_user, init_db, update_user_name, update_user_resume, update_user_state
from twilio_utils import send_whatsapp_message

# ---------------------------------------------------------------------------
#  Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  FastAPI app with startup event to initialise the database
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup."""
    init_db()
    logger.info("🚀 WhatsApp AI Job Agent is running!")
    yield
    logger.info("👋 Shutting down...")


app = FastAPI(
    title="WhatsApp AI Job Agent",
    description="A WhatsApp-based AI assistant that helps users find jobs matching their resume.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
#  Health check
# ---------------------------------------------------------------------------

@app.get("/")
def health_check():
    """Simple health check endpoint."""
    return {
        "status": "running",
        "service": "WhatsApp AI Job Agent",
        "message": "Send a WhatsApp message to get started!",
    }


# ---------------------------------------------------------------------------
#  Help message
# ---------------------------------------------------------------------------

HELP_MESSAGE = """🤖 *WhatsApp AI Job Agent*

Here's what I can do:

📝 */new* — Register as a new user
✏️ */update* — Update your resume
👤 */profile* — View your extracted profile
🔍 *search job for me* — Find matching jobs
❓ */help* — Show this help message

_Start with /new to create your profile!_"""


# ---------------------------------------------------------------------------
#  Background task: search jobs and send results
# ---------------------------------------------------------------------------

def _background_job_search(phone_number: str, user_name: str, parsed_data: dict, resume_text: str):
    """Run job search in the background and send results via Twilio."""
    try:
        logger.info("Background job search started for %s", phone_number)
        jobs = search_jobs(parsed_data, resume_text)
        
        # 1. Send the summary message
        summary_msg = format_job_summary(jobs)
        send_whatsapp_message(to=phone_number, body=summary_msg)
        
        # 2. Send detailed card for each job (includes description and draft email)
        for i, job in enumerate(jobs, 1):
            job_card = format_single_job_card(job, i, len(jobs), user_name, parsed_data)
            send_whatsapp_message(to=phone_number, body=job_card)

        logger.info("Job search results sent to %s (%d jobs)", phone_number, len(jobs))
    except Exception as e:
        logger.error("Background job search failed for %s: %s", phone_number, e)
        try:
            send_whatsapp_message(
                to=phone_number,
                body="⚠️ Sorry, something went wrong while searching for jobs. Please try again later.",
            )
        except Exception:
            logger.error("Failed to send error message to %s", phone_number)


# ---------------------------------------------------------------------------
#  Twilio webhook
# ---------------------------------------------------------------------------

@app.post("/whatsapp")
async def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    Body: str = Form(""),
    From: str = Form(""),
):
    """
    Handle incoming WhatsApp messages from Twilio.

    Twilio sends a POST with form data including:
      - Body: the message text
      - From: the sender's number (e.g. "whatsapp:+919876543210")
    """
    # Clean up inputs
    message = Body.strip()
    phone_number = From.strip()

    logger.info("Incoming message from %s: '%s'", phone_number, message[:100])

    # Create a TwiML response object
    twiml = MessagingResponse()

    # Handle empty messages
    if not message:
        twiml.message("👋 Hi there! Send */help* to see what I can do.")
        return Response(content=str(twiml), media_type="application/xml")

    # Normalise the message for command matching
    message_lower = message.lower().strip()

    # -----------------------------------------------------------------------
    #  /help command — always accessible
    # -----------------------------------------------------------------------
    if message_lower in ("/help", "help", "hi", "hello", "hey"):
        twiml.message(HELP_MESSAGE)
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  /new command — start registration
    # -----------------------------------------------------------------------
    if message_lower == "/new":
        existing_user = get_user(phone_number)

        if existing_user and existing_user["state"] == "READY":
            twiml.message(
                f"👋 Welcome back, *{existing_user['name']}*!\n\n"
                "You already have a profile. Use:\n"
                "• */profile* to view it\n"
                "• */update* to change your resume\n"
                "• *search job for me* to find jobs"
            )
            return Response(content=str(twiml), media_type="application/xml")

        # Create new user or reset existing one
        if existing_user:
            # Reset their state
            update_user_state(phone_number, "WAITING_FOR_NAME")
        else:
            create_user(phone_number, state="WAITING_FOR_NAME")

        twiml.message(
            "🎉 *Welcome to the AI Job Agent!*\n\n"
            "Let's set up your profile.\n\n"
            "📛 *What is your name?*"
        )
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  Fetch current user (for all other commands, user must exist)
    # -----------------------------------------------------------------------
    user = get_user(phone_number)

    # If user doesn't exist, prompt them to register
    if user is None:
        twiml.message(
            "👋 Hi! I don't have your profile yet.\n\n"
            "Send */new* to get started!"
        )
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  State machine: WAITING_FOR_NAME
    # -----------------------------------------------------------------------
    if user["state"] == "WAITING_FOR_NAME":
        name = message.strip()
        if len(name) < 2 or len(name) > 50:
            twiml.message("❌ Please enter a valid name (2-50 characters).")
            return Response(content=str(twiml), media_type="application/xml")

        update_user_name(phone_number, name)
        twiml.message(
            f"✅ Great, *{name}*!\n\n"
            "Now paste your *resume text* below. 📄\n\n"
            "_Include your skills, experience, projects, and education. "
            "The more detail, the better the job matches!_"
        )
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  State machine: WAITING_FOR_RESUME
    # -----------------------------------------------------------------------
    if user["state"] == "WAITING_FOR_RESUME":
        resume_text = message.strip()

        if len(resume_text) < 50:
            twiml.message(
                "❌ That seems too short for a resume.\n\n"
                "Please paste your full resume text (at least 50 characters) "
                "including skills, experience, and education.\n\n"
                "💡 _You can send up to ~8000 words in a single message!_"
            )
            return Response(content=str(twiml), media_type="application/xml")

        if len(resume_text) > MAX_RESUME_LENGTH:
            twiml.message(
                f"❌ That resume is too long ({len(resume_text):,} characters).\n\n"
                f"Please keep it under {MAX_RESUME_LENGTH:,} characters (~8000 words).\n"
                "Tip: Remove extra formatting and keep just the key details."
            )
            return Response(content=str(twiml), media_type="application/xml")

        # Parse the resume
        parsed_data = parse_resume(resume_text)
        update_user_resume(phone_number, resume_text, parsed_data)

        skills_preview = ", ".join(parsed_data.get("skills", [])[:8])
        role = parsed_data.get("role", "N/A")
        exp = parsed_data.get("experience_years", 0)

        twiml.message(
            "✅ *Profile saved successfully!* 🎉\n\n"
            f"📋 *Here's what I extracted:*\n"
            f"💼 Role: {role}\n"
            f"📅 Experience: {exp} years\n"
            f"🛠️ Skills: {skills_preview or 'None detected'}\n\n"
            "You can now:\n"
            "• Send *search job for me* to find matching jobs\n"
            "• Send */profile* to see your full profile\n"
            "• Send */update* to change your resume"
        )
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  From here, user state must be READY
    # -----------------------------------------------------------------------
    if user["state"] != "READY":
        twiml.message(
            "⚠️ Something seems off with your profile.\n\n"
            "Send */new* to start fresh."
        )
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  /profile command
    # -----------------------------------------------------------------------
    if message_lower == "/profile":
        profile_msg = format_profile(user)
        twiml.message(profile_msg)
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  /update command — re-enter resume
    # -----------------------------------------------------------------------
    if message_lower == "/update":
        update_user_state(phone_number, "WAITING_FOR_RESUME")
        twiml.message(
            "✏️ *Update mode!*\n\n"
            "Paste your updated resume text below. 📄\n\n"
            "_Your previous resume will be replaced with the new one._"
        )
        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  Search jobs command
    # -----------------------------------------------------------------------
    search_triggers = [
        "search job", "search jobs", "find job", "find jobs",
        "search job for me", "find job for me", "get jobs",
        "job search", "find me a job", "look for jobs",
    ]
    if any(trigger in message_lower for trigger in search_triggers):
        # Send immediate acknowledgment, then process in background
        twiml.message(
            "🔍 *Searching for jobs matching your profile...*\n\n"
            "⏳ This may take a moment. I'll send the results shortly!"
        )

        # Launch job search as a background task
        background_tasks.add_task(
            _background_job_search,
            phone_number,
            user.get("name", "Candidate"),
            user["parsed_data"],
            user.get("resume_text", ""),
        )

        return Response(content=str(twiml), media_type="application/xml")

    # -----------------------------------------------------------------------
    #  Unknown command fallback
    # -----------------------------------------------------------------------
    twiml.message(
        "🤔 I didn't understand that.\n\n"
        "Try one of these commands:\n"
        "• */profile* — View your profile\n"
        "• */update* — Update your resume\n"
        "• *search job for me* — Find matching jobs\n"
        "• */help* — See all commands"
    )
    return Response(content=str(twiml), media_type="application/xml")


# ---------------------------------------------------------------------------
#  Run with: uvicorn main:app --reload --port 8000
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
