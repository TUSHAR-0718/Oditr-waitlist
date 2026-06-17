# MongoDB to Supabase Migration - Waitlist Logging & Confirmation Emails

## Overview
Successfully migrated the Oditr waitlist backend from MongoDB to Supabase PostgreSQL while maintaining Resend email confirmations for waitlisters.

## Changes Made

### 1. Database Schema (Supabase)
Created the `public.waitlist` table with the following structure:

```sql
CREATE TABLE public.waitlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  referral_code TEXT UNIQUE NOT NULL,
  referral_count INT DEFAULT 0,
  referred_by TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
- `idx_waitlist_email` - Fast email lookups
- `idx_waitlist_referral_code` - Fast referral code queries
- `idx_waitlist_created_at` - Efficient sorting by creation time

### 2. Backend Code Changes

#### `backend/server.py`
**Removed:**
- MongoDB imports (`motor`, `AsyncIOMotorClient`)
- IPv4 monkeypatch for MongoDB Atlas
- MongoDB connection initialization
- MongoDB certifi CA bundle configuration

**Added:**
- Supabase client initialization using `create_client()`
- Environment variable loading for `SUPABASE_URL` and `SUPABASE_ANON_KEY`

**Updated Functions:**
- `unique_ref_code()` - Changed from MongoDB `find_one()` to Supabase `.select().eq()`
- `compute_position()` - Changed from MongoDB aggregation to Supabase `.gt()` and `.lt()` filters
- `join_waitlist()` - Complete refactor to use Supabase CRUD operations:
  - Duplicate email check using `.eq().execute()`
  - Referrer validation using referral code lookup
  - Entry insertion using `.insert().execute()`
  - Referral count increment using `.update().execute()`
- `waitlist_count()` - Changed to Supabase count with `.select("id", count="exact")`
- `waitlist_by_code()` - Changed from MongoDB to Supabase query with `.eq()`
- `list_signups()` - Updated pagination using `.range()` for skip/limit
- Removed MongoDB startup/shutdown event handlers

#### `backend/requirements.txt`
**Removed:**
- `pymongo==4.5.0`
- `motor==3.3.1`

**Added:**
- `supabase>=2.0.0`

#### `backend/email_service.py`
**No changes required** - Already configured for Resend email service

### 3. Environment Variables

**Supabase (Required):**
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anonymous key for client auth

**Email Configuration (Required for confirmations):**
- `RESEND_API_KEY` - Your Resend API key for sending emails
- `EMAIL_FROM` - Sender email address (e.g., "Oditr <noreply@oditr.com>")
- `SITE_URL` - Base URL for referral links in confirmation emails

**Optional (Already configured):**
- `ADMIN_USERNAME` - Admin login username
- `ADMIN_PASSWORD_HASH` - Bcrypt hash of admin password
- `DB_NAME` - Database name (default: postgres)

### 4. Features Maintained

✅ **Waitlist Registration** - Users can join with email
✅ **Referral System** - Unique referral codes generated for each user
✅ **Position Tracking** - Users ranked by referral count and signup time
✅ **Duplicate Prevention** - Prevents duplicate email registrations
✅ **Referral Counting** - Tracks referral count for leaderboard positioning
✅ **Email Confirmations** - Sends confirmation with position and referral link via Resend
✅ **Admin Dashboard** - List all signups with pagination
✅ **JWT Authentication** - Admin endpoints protected with token-based auth

## How Confirmation Emails Work

When a user joins the waitlist:

1. **Backend receives** - POST request to `/waitlist` endpoint
2. **Entry is created** - User added to Supabase with generated referral code
3. **Position calculated** - Computed based on referral count and signup time
4. **Email queued** - Non-blocking async call to Resend
5. **Confirmation sent** - HTML email with:
   - Current waitlist position
   - Unique referral link
   - Share encouragement

The email service handles failures gracefully - if Resend is unavailable, the signup completes successfully and the error is logged.

## Testing the Migration

```bash
# Install dependencies
cd backend
source .venv/bin/activate
pip install -r requirements.txt

# Verify backend imports
python -c "from server import app, supabase; print('✓ Ready')"

# Start backend
uvicorn server:app --reload --port 8000
```

## API Endpoints

**Waitlist Management:**
- `POST /api/waitlist` - Join waitlist (email, optional referral code)
- `GET /api/waitlist/count` - Get total waitlist count
- `GET /api/waitlist/code/{code}` - Get user info by referral code

**Admin (Requires Auth):**
- `GET /api/admin/signups?page=1&limit=50` - List all signups with pagination

## Future Enhancements

- Add RLS (Row Level Security) policies for frontend access
- Implement waitlist status tracking (pending, early-access, inactive)
- Add email preference management
- Create admin dashboard for exporting waitlist data
- Add webhooks for downstream integrations
