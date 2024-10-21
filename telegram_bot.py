import os
import json
import asyncio
import firebase_admin
from firebase_admin import credentials, firestore, storage, messaging
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import PeerChannel
import sqlite3
import re
import uuid
from googletrans import Translator
from datetime import datetime
import base64

# Custom JSON encoder to handle datetime and bytes objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, bytes):
            return base64.b64encode(obj).decode('utf-8')
        return super(DateTimeEncoder, self).default(obj)

# Enable WAL mode for SQLite
def enable_wal_mode(session_name):
    conn = sqlite3.connect(f'{session_name}.session')
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.close()

# Enable WAL mode before using the session
enable_wal_mode('session_file_name')

# Fetching sensitive configuration from environment variables
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')
username = os.getenv('USERNAME')

# Create a Telegram client
client = TelegramClient('session_file_name', api_id, api_hash)

# Initialize Firestore and Firebase Admin
if not firebase_admin._apps:
    cred = credentials.Certificate('https://github.com/melhem12/firebaseconfigtelegrambot/blob/main/lebanese-news-firebase-adminsdk-7swjw-d568e8ecee.json')
    firebase_admin.initialize_app(cred, {'storageBucket': 'your-bucket-url'})

db = firestore.client()  # Initialize Firestore client
db_lock = asyncio.Lock()  # Lock to ensure only one task accesses the DB at a time

# Function to translate text from Arabic to English
def translate_arabic_to_english(text):
    try:
        translator = Translator()
        translated_text = translator.translate(text, src='ar', dest='en')
        return translated_text.text
    except Exception as e:
        print("Translation error:", e)
        return None

# Main function to fetch messages and process them
async def main():
    await client.start()
    print("Client Created")

    # Ensure you're authorized
    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        try:
            await client.sign_in(phone, input('Enter the code: '))
        except SessionPasswordNeededError:
            await client.sign_in(password=input('Password: '))

    entity = 'https://t.me/Lebanon_24'
    my_channel = await client.get_entity(entity)

    last_message_id = None

    history = await client(GetHistoryRequest(
        peer=my_channel,
        offset_id=0,
        offset_date=None,
        add_offset=0,
        limit=1,
        max_id=0,
        min_id=0,
        hash=0
    ))

    if history.messages:
        new_message = history.messages[0].to_dict()
        new_message_id = new_message['id']
        if new_message_id != last_message_id:
            print("New message found, updating...")

            message_content = new_message.get('message', '').strip()
            if not message_content:
                print("Empty message content. Skipping processing.")
                return

            message_date = new_message.get('date')
            message_content_no_links = re.sub(r'https?://\S+', '', message_content)

            title = ' '.join(message_content_no_links.split()[:7])

            firestore_document = {
                'title': title,
                'category': 'hot_news',
                'content': message_content_no_links,
                'content_en': translate_arabic_to_english(message_content_no_links),
                'title_en': translate_arabic_to_english(title),
                'publishedAt': message_date,
                'articleUrl': 'LEB News'
            }

            async with db_lock:
                # Save the document to Firestore
                doc_ref = db.collection('news').document(str(new_message_id))
                doc_ref.set(firestore_document)
                print("Message saved to Firestore")

                # Send notification with topic "news"
                topic = "all"
                notification = messaging.Notification(
                    title=title,
                    body="التفاصيل داخل التطبيق"
                )
                message = messaging.Message(
                    notification=notification,
                    topic=topic,
                )

                # Send the message
                try:
                    response = messaging.send(message)
                    print('Notification sent successfully:', response)
                except Exception as e:
                    print('Failed to send notification:', e)
        else:
            print("No new messages.")

# Use async with client to ensure proper asynchronous context
async def run_client():
    async with client:
        await main()

# Run the client
asyncio.run(run_client())
