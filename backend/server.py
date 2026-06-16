from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from email_service import send_waitlist_confirmation
import os
import logging
import secrets
import string
import socket
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional
import uuid
from datetime import datetime, timezone
import certifi

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from auth import create_access_token, verify_token, pwd_context, ADMIN_USERNAME, ADMIN_PASSWORD_HASH

# --- MONKEYPATCH: Force IPv4 for MongoDB Atlas ---
# Some ISPs use DNS64/NAT64 which resolves Atlas to IPv6. 
# Atlas Free clusters (M0) drop IPv6 connections, causing TLSV1_ALERT_INTERNAL_ERROR.
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [res for res in responses if res[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# -------------------------------------------------

mongo_url = os.environ['MONGO_URL']
# Use certifi's CA bundle to ensure proper TLS 1.2+ with MongoDB Atlas
client = AsyncIOMotorClient(mongo_url, tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]

# Display baseline so the counter starts at a credible community size
WAITLIST_BASELINE = int(os.environ.get('WAITLIST_BASELINE', '13'))

app = FastAPI()
api_router = APIRouter(prefix="/api")

REF_ALPHABET = string.ascii_lowercase + string.digits


def gen_ref_code(length: int = 7) -> str:
    return "".join(secrets.choice(REF_ALPHABET) for _ in range(length))


async def unique_ref_code() -> str:
    for _ in range(8):
        code = gen_ref_code()
        existing = await db.waitlist.find_one({"referral_code": code}, {"_id": 0, "id": 1})
        if not existing:
            return code
    # fallback to longer code
    return gen_ref_code(10)


async def compute_position(entry: dict) -> int:
    """Position = baseline + 1 + (# of entries with more referrals OR same referrals but earlier created_at)."""
    ref_count = entry.get("referral_count", 0)
    created_at = entry["created_at"]
    # All stored entries persist created_at as an ISO string. Normalize to string
    # so $lt comparison works regardless of the input type.
    if isinstance(created_at, datetime):
        created_at_iso = created_at.isoformat()
    else:
        created_at_iso = str(created_at)
    higher = await db.waitlist.count_documents({"referral_count": {"$gt": ref_count}})
    same_earlier = await db.waitlist.count_documents({
        "referral_count": ref_count,
        "created_at": {"$lt": created_at_iso},
    })
    return higher + same_earlier + 1 + WAITLIST_BASELINE


# ------------ Models ------------
class WaitlistCreate(BaseModel):
    email: EmailStr
    ref: Optional[str] = None


class WaitlistResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: EmailStr
    created_at: datetime
    referral_code: str
    referral_count: int
    referred_by: Optional[str] = None
    position: int
    count: int
    is_duplicate: bool = False


class WaitlistCountResponse(BaseModel):
    count: int


# ------------ Routes ------------
@api_router.get("/")
async def root():
    return {"message": "Øditr API", "status": "ok"}


@api_router.post("/waitlist", response_model=WaitlistResponse)
async def join_waitlist(payload: WaitlistCreate):
    email_normalized = payload.email.lower().strip()
    ref_code = (payload.ref or "").strip().lower() or None

    try:
        existing = await db.waitlist.find_one({"email": email_normalized}, {"_id": 0})
    except Exception as e:
        logger.exception("Database error during find_one")
        raise HTTPException(status_code=500, detail="Database connection failed")

    if existing:
        # backfill referral_code if older record lacked one
        if not existing.get("referral_code"):
            new_code = await unique_ref_code()
            await db.waitlist.update_one(
                {"id": existing["id"]}, {"$set": {"referral_code": new_code}}
            )
            existing["referral_code"] = new_code
        existing.setdefault("referral_count", 0)
        existing.setdefault("referred_by", None)
        if isinstance(existing["created_at"], str):
            existing["created_at"] = datetime.fromisoformat(existing["created_at"])
        position = await compute_position(existing)
        count = await db.waitlist.count_documents({}) + WAITLIST_BASELINE
        return WaitlistResponse(
            id=existing["id"],
            email=existing["email"],
            created_at=existing["created_at"],
            referral_code=existing["referral_code"],
            referral_count=existing["referral_count"],
            referred_by=existing.get("referred_by"),
            position=position,
            count=count,
            is_duplicate=True,
        )

    # validate referrer
    referred_by = None
    if ref_code:
        referrer = await db.waitlist.find_one({"referral_code": ref_code}, {"_id": 0, "id": 1})
        if referrer:
            referred_by = ref_code

    new_code = await unique_ref_code()
    now = datetime.now(timezone.utc)
    entry = {
        "id": str(uuid.uuid4()),
        "email": email_normalized,
        "created_at": now.isoformat(),
        "referral_code": new_code,
        "referral_count": 0,
        "referred_by": referred_by,
    }
    await db.waitlist.insert_one(entry)

    if referred_by:
        await db.waitlist.update_one(
            {"referral_code": referred_by},
            {"$inc": {"referral_count": 1}},
        )

    entry_for_position = {**entry, "created_at": now}
    position = await compute_position(entry_for_position)
    count = await db.waitlist.count_documents({}) + WAITLIST_BASELINE

    # Send confirmation email (non-blocking, non-fatal)
    await send_waitlist_confirmation(email_normalized, position, new_code)

    return WaitlistResponse(
        id=entry["id"],
        email=entry["email"],
        created_at=now,
        referral_code=new_code,
        referral_count=0,
        referred_by=referred_by,
        position=position,
        count=count,
        is_duplicate=False,
    )


@api_router.get("/waitlist/count", response_model=WaitlistCountResponse)
async def waitlist_count():
    count = await db.waitlist.count_documents({})
    return WaitlistCountResponse(count=count + WAITLIST_BASELINE)


@api_router.get("/waitlist/code/{code}", response_model=WaitlistResponse)
async def waitlist_by_code(code: str):
    code = code.strip().lower()
    entry = await db.waitlist.find_one({"referral_code": code}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Referral code not found")
    if isinstance(entry["created_at"], str):
        entry["created_at"] = datetime.fromisoformat(entry["created_at"])
    entry.setdefault("referral_count", 0)
    entry.setdefault("referred_by", None)
    position = await compute_position(entry)
    count = await db.waitlist.count_documents({}) + WAITLIST_BASELINE
    return WaitlistResponse(
        id=entry["id"],
        email=entry["email"],
        created_at=entry["created_at"],
        referral_code=entry["referral_code"],
        referral_count=entry["referral_count"],
        referred_by=entry.get("referred_by"),
        position=position,
        count=count,
    )


@api_router.post("/admin/login")
async def admin_login(form: OAuth2PasswordRequestForm = Depends()):
    if form.username != ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(form.password, ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": form.username})
    return {"access_token": token, "token_type": "bearer"}


@api_router.get("/admin/signups")
async def list_signups(
    page: int = 1,
    limit: int = 50,
    _: str = Depends(verify_token)
):
    skip = (page - 1) * limit
    cursor = db.waitlist.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    entries = await cursor.to_list(length=limit)
    total = await db.waitlist.count_documents({})
    return {"total": total, "page": page, "entries": entries}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def backfill_waitlist():
    try:
        # Older entries may pre-date the referral fields. Backfill defaults.
        await db.waitlist.update_many(
            {"referral_count": {"$exists": False}}, {"$set": {"referral_count": 0}}
        )
        await db.waitlist.update_many(
            {"referred_by": {"$exists": False}}, {"$set": {"referred_by": None}}
        )
        # Backfill referral_code for any entries missing one
        cursor = db.waitlist.find({"referral_code": {"$in": [None, ""]}}, {"_id": 0, "id": 1})
        async for entry in cursor:
            code = await unique_ref_code()
            await db.waitlist.update_one({"id": entry["id"]}, {"$set": {"referral_code": code}})
        cursor2 = db.waitlist.find({"referral_code": {"$exists": False}}, {"_id": 0, "id": 1})
        async for entry in cursor2:
            code = await unique_ref_code()
            await db.waitlist.update_one({"id": entry["id"]}, {"$set": {"referral_code": code}})
    except Exception as e:
        logger.warning(f"Startup backfill skipped (will retry on next request): {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
