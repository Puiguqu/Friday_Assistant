import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv
from telegram import Bot
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

# Ollama API
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/chat")  # Use a default URL if not in .env

def process_with_ollama(email_body, model="llama3.2"):
    """
    Summarize the email in 2 sentences using Ollama locally.
    """
    try:
        # Define the summarization prompt
        prompt = f"Summarize this email in 2 sentences:\n\n{email_body}"

        # Send the request to the Ollama server
        response = requests.post(
            OLLAMA_API_URL,
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            stream=True,  # Enable streaming response
        )
        response.raise_for_status()

        # Accumulate the content from the stream
        full_content = ""
        for line in response.iter_lines():
            if line:
                try:
                    # Parse the JSON object
                    json_line = json.loads(line)
                    # Append the message content to the full content
                    full_content += json_line.get("message", {}).get("content", "")
                except json.JSONDecodeError:
                    print(f"Failed to parse line as JSON: {line}")

        return full_content.strip()

    except requests.exceptions.RequestException as e:
        print(f"Ollama API error: {e}")
        return "Unable to process email due to a local Ollama issue."

async def send_telegram_message(bot, chat_id, message):
    """Send a message asynchronously via Telegram."""
    try:
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

async def fetch_emails_and_process():
    """Fetch unread emails, summarize, and categorize them with Ollama."""
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

        # Initialize Telegram bot
        bot = Bot(token=TELEGRAM_TOKEN)

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

                    # Use Ollama for summarization, categorization, and response requirement
                    summary = process_with_ollama(body)
                    category = process_with_ollama(
                        f"Categorize this email into one of the following categories: News/Politics, Work, Personal, Invoice, or Other. Provide the category only."
                    )
                    response_required = process_with_ollama(
                        "Does this email require a response? Answer 'Yes' or 'No' only."
                    )

                    # Prepare notification
                    notification = (
                        f"📧 *New Email*\n"
                        f"*From*: {sender}\n"
                        f"*Subject*: {subject}\n"
                        f"*Category*: {category}\n"
                        f"*Summary*: {summary}\n"
                        f"*Response Required*: {response_required}"
                    )

                    # Send Telegram notification
                    await send_telegram_message(bot, TELEGRAM_CHAT_ID, notification)
                    print(f"Notification sent for email: {subject}")

        # Logout
        mail.logout()

    except Exception as e:
        print(f"An error occurred: {e}")

async def run_continuously():
    """Run the email processing function continuously with a delay."""
    while True:
        print(f"Checking for new emails at {time.strftime('%Y-%m-%d %H:%M:%S')}...")
        await fetch_emails_and_process()
        print(f"Waiting for the next check...")
        await asyncio.sleep(300)  # Wait for 5 minutes before checking again

# Run the continuous loop
asyncio.run(run_continuously())
