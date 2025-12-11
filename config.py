import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))
