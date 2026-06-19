from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from supabase import create_client
from email_service import send_waitlist_confirmation
import os
import logging
import secrets
import string
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional
import uuid
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from auth import create_access_token, verify_token, pwd_context, ADMIN_USERNAME, ADMIN_PASSWORD_HASH

# Initialize Supabase client
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        response = supabase.table("waitlist").select("id").eq("referral_code", code).execute()
        if not response.data:
            return code
    # fallback to longer code
    return gen_ref_code(10)


async def compute_position(entry: dict) -> int:
    """Position = baseline + 1 + (# of entries with more referrals OR same referrals but earlier created_at)."""
    ref_count = entry.get("referral_count", 0)
    created_at = entry["created_at"]
    # Normalize to ISO string for comparison
    if isinstance(created_at, datetime):
        created_at_iso = created_at.isoformat()
    else:
        created_at_iso = str(created_at)
    
    # Count entries with more referrals
    higher_response = supabase.table("waitlist").select("id", count="exact").gt("referral_count", ref_count).execute()
    higher = higher_response.count or 0
    
    # Count entries with same referrals but earlier created_at
    same_earlier_response = supabase.table("waitlist").select("id", count="exact").eq("referral_count", ref_count).lt("created_at", created_at_iso).execute()
    same_earlier = same_earlier_response.count or 0
    
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
        # Check if email already exists
        existing_response = supabase.table("waitlist").select("*").eq("email", email_normalized).execute()
        existing = existing_response.data[0] if existing_response.data else None
    except Exception as e:
        logger.exception("Database error during lookup")
        raise HTTPException(status_code=500, detail="Database connection failed")

    if existing:
        # backfill referral_code if older record lacked one
        if not existing.get("referral_code"):
            new_code = await unique_ref_code()
            supabase.table("waitlist").update({"referral_code": new_code}).eq("id", existing["id"]).execute()
            existing["referral_code"] = new_code
        existing.setdefault("referral_count", 0)
        existing.setdefault("referred_by", None)
        if isinstance(existing["created_at"], str):
            existing["created_at"] = datetime.fromisoformat(existing["created_at"])
        position = await compute_position(existing)
        count_response = supabase.table("waitlist").select("id", count="exact").execute()
        count = (count_response.count or 0) + WAITLIST_BASELINE
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
        referrer_response = supabase.table("waitlist").select("id").eq("referral_code", ref_code).execute()
        if referrer_response.data:
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
    supabase.table("waitlist").insert(entry).execute()

    if referred_by:
        # Increment referral count for the referrer
        referrer_response = supabase.table("waitlist").select("referral_count").eq("referral_code", referred_by).execute()
        if referrer_response.data:
            current_count = referrer_response.data[0].get("referral_count", 0)
            supabase.table("waitlist").update({"referral_count": current_count + 1}).eq("referral_code", referred_by).execute()

    entry_for_position = {**entry, "created_at": now}
    position = await compute_position(entry_for_position)
    count_response = supabase.table("waitlist").select("id", count="exact").execute()
    count = (count_response.count or 0) + WAITLIST_BASELINE

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
    response = supabase.table("waitlist").select("id", count="exact").execute()
    count = (response.count or 0) + WAITLIST_BASELINE
    return WaitlistCountResponse(count=count)


@api_router.get("/waitlist/code/{code}", response_model=WaitlistResponse)
async def waitlist_by_code(code: str):
    code = code.strip().lower()
    response = supabase.table("waitlist").select("*").eq("referral_code", code).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Referral code not found")
    entry = response.data[0]
    if isinstance(entry["created_at"], str):
        entry["created_at"] = datetime.fromisoformat(entry["created_at"])
    entry.setdefault("referral_count", 0)
    entry.setdefault("referred_by", None)
    position = await compute_position(entry)
    count_response = supabase.table("waitlist").select("id", count="exact").execute()
    count = (count_response.count or 0) + WAITLIST_BASELINE
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
    response = supabase.table("waitlist").select("*").order("created_at", desc=True).range(skip, skip + limit - 1).execute()
    entries = response.data or []
    total_response = supabase.table("waitlist").select("id", count="exact").execute()
    total = total_response.count or 0
    return {"total": total, "page": page, "entries": entries}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def backfill_waitlist():
    try:
        # Backfill referral_code for any entries missing one
        missing_code_response = supabase.table("waitlist").select("id").is_("referral_code", "null").execute()
        for entry in missing_code_response.data or []:
            code = await unique_ref_code()
            supabase.table("waitlist").update({"referral_code": code}).eq("id", entry["id"]).execute()
    except Exception as e:
        logger.warning(f"Startup backfill skipped (will retry on next request): {e}")
