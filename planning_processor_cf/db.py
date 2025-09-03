# db.py
import motor.motor_asyncio
import os
from dotenv import load_dotenv
import certifi

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
MONGO_DB = os.getenv("MONGODB_DB", "scm_chat_db")

try:
    # 2. GET THE PATH TO THE TRUSTED CERTIFICATES
    ca = certifi.where()

    # 3. ADD THE tlsCAFile PARAMETER TO YOUR CLIENT
    client = motor.motor_asyncio.AsyncIOMotorClient(
        MONGO_URI,
        tlsCAFile=ca
    )
    
    db = client[MONGO_DB]
    print("✅ Successfully connected to MongoDB Atlas.")

except Exception as e:
    print(f"❌ Failed to connect to MongoDB: {e}")
    db = None
