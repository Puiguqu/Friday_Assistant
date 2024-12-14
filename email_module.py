import imaplib
import email
from email.header import decode_header
import os
import asyncio
import requests
from dotenv import load_dotenv
from telegram.ext import Application
from telegram.constants import ParseMode

# Load environment variables
load_dotenv()

# Telegram bot credentials
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Google Gemini API
GEMINI_API_URL = os.getenv("GEMINI_API_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Email accounts configuration (add multiple accounts here)
EMAIL_ACCOUNTS = [
    {"email": os.getenv("EMAIL1"), "password": os.getenv("EMAIL_PASSWORD1"), "imap_server": "imap.gmail.com"},
    {"email": os.getenv("EMAIL2"), "password": os.getenv("EMAIL_PASSWORD2"), "imap_server": "imap.gmail.com"}
]

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
    """Fetch unread emails from multiple accounts, summarize, and categorize them."""
    for account in EMAIL_ACCOUNTS:
        try:
            email_address = account["email"]
            password = account["password"]
            imap_server = account["imap_server"]

            print(f"Checking emails for account: {email_address}")

            # Connect to the email server
            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(email_address, password)
            mail.select("inbox")

            # Search for unread emails
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK":
                print(f"No unread emails for {email_address}.")
                continue

            email_ids = messages[0].split()
            print(f"Found {len(email_ids)} unread emails for {email_address}.")

            # Process each email
            for email_id in email_ids[:3]:  # Limit to 3 emails per account
                res, msg = mail.fetch(email_id, "(RFC822)")
                if res != "OK":
                    print(f"Failed to fetch email {email_id} for {email_address}")
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
                            f"*Account*: {email_address}\n"
                            f"*From*: {sender}\n"
                            f"*Subject*: {subject}\n"
                            f"*Category*: {category}\n"
                            f"*Summary*: {summary}\n"
                            f"*Response Required*: {response_required}"
                        )

                        # Send Telegram notification
                        await send_telegram_message(application, TELEGRAM_CHAT_ID, notification)
                        print(f"Notification sent for email: {subject} from account {email_address}")

            # Logout
            mail.logout()

        except Exception as e:
            print(f"An error occurred for account {account['email']}: {e}")

async def start_email_module(application):
    """Run the email processing function continuously."""
    while True:
        print(f"Checking for new emails...")
        await fetch_emails_and_process(application)
        await asyncio.sleep(300)  # Check every 5 minutes

def register_email_module(application: Application):
    """Register the email module with the application."""
    application.create_task(start_email_module(application))
