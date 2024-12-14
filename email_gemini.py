import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler
from telegram.constants import ParseMode
import asyncio
import requests
import time
import os
import json

# Load environment variables
load_dotenv()

# Email credentials
EMAIL = os.getenv("EMAIL")  # Replace with your email in the .env file
PASSWORD = os.getenv("EMAIL_PASSWORD")  # Replace with your email password in the .env file
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

# Telegram bot credentials
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Replace with your Telegram bot token in the .env file
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Replace with your chat ID in the .env file

# Google Gemini API
GEMINI_API_URL = os.getenv("GEMINI_API_URL")  # Replace with your Google Gemini API URL in the .env file
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Replace with your Google Gemini API key in the .env file

def process_with_gemini(email_body, prompt):
    """
    Process the email content using Google Gemini API.
    """
    try:
        headers = {
            "Authorization": f"Bearer {GEMINI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": email_body,
            "prompt": prompt
        }
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload)
        response.raise_for_status()

        # Extract response
        result = response.json().get("output", "Unable to process email.")
        return result.strip()

    except requests.exceptions.RequestException as e:
        print(f"Google Gemini API error: {e}")
        return "Unable to process email due to an API issue."

async def send_telegram_message(application, chat_id, message):
    """Send a message asynchronously via Telegram."""
    try:
        await application.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

async def fetch_emails_and_process(application):
    """Fetch unread emails, summarize, and categorize them with Google Gemini."""
    try:
        # Connect to the email server
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        # Search for unread emails
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK":
            print("No unread emails.")
            return

        email_ids = messages[0].split()
        print(f"Found {len(email_ids)} unread emails.")

        # Process each email
        for email_id in email_ids[:3]:  # Limit to 3 emails to reduce processing time
            res, msg = mail.fetch(email_id, "(RFC822)")
            if res != "OK":
                print(f"Failed to fetch email {email_id}")
                continue

            for response_part in msg:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Decode subject
                    subject = decode_header(msg["Subject"])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()

                    # Decode sender
                    sender = msg.get("From")

                    # Get the email body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = msg.get_payload(decode=True).decode()

                    # Use Google Gemini for summarization, categorization, and response requirement
                    summary = process_with_gemini(body, "Summarize this email in 2 sentences.")
                    category = process_with_gemini(
                        body, "Categorize this email into one of the following categories: News/Politics, Work, Personal, Invoice, or Other. Provide the category only."
                    )
                    response_required = process_with_gemini(
                        body, "Does this email require a response? Answer 'Yes' or 'No' only."
                    )

                    # Prepare notification
                    notification = (
                        f"\U0001F4E7 *New Email*\n"
                        f"*From*: {sender}\n"
                        f"*Subject*: {subject}\n"
                        f"*Category*: {category}\n"
                        f"*Summary*: {summary}\n"
                        f"*Response Required*: {response_required}"
                    )

                    # Send Telegram notification
                    await send_telegram_message(application, TELEGRAM_CHAT_ID, notification)
                    print(f"Notification sent for email: {subject}")

        # Logout
        mail.logout()

    except Exception as e:
        print(f"An error occurred: {e}")

async def run_continuously(application):
    """Run the email processing function continuously with a delay."""
    while True:
        print(f"Checking for new emails at {time.strftime('%Y-%m-%d %H:%M:%S')}...")
        await fetch_emails_and_process(application)
        print(f"Waiting for the next check...")
        await asyncio.sleep(300)  # Wait for 5 minutes before checking again

if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Start the continuous loop
    application.run_async(run_continuously(application))
    application.run_polling()}]}
