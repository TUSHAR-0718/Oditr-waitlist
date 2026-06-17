# Supabase & Resend Integration Setup

## Overview
Your waitlist application has been successfully migrated from MongoDB to Supabase PostgreSQL with Resend for email confirmations.

## Database Schema

### Waitlist Table
The `public.waitlist` table stores all waitlist signups with the following structure:

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

**Fields:**
- `id`: Unique identifier for each waitlist entry
- `email`: User's email address (unique)
- `referral_code`: Unique referral code for sharing
- `referral_count`: Number of successful referrals (moves user up in queue)
- `referred_by`: The referral code of the person who referred this user
- `created_at`: Timestamp when user joined the waitlist
- `updated_at`: Last update timestamp

**Indexes:**
- `idx_waitlist_email`: Fast lookup by email
- `idx_waitlist_referral_code`: Fast lookup by referral code
- `idx_waitlist_created_at`: Fast sorting by creation date (for position calculation)

## Environment Variables Required

Set these in your Vercel project settings:

1. **SUPABASE_URL** - Your Supabase project URL
   - Format: `https://your-project.supabase.co`
   - Found in: Supabase Dashboard → Settings → API

2. **SUPABASE_ANON_KEY** - Supabase anonymous/public key
   - Found in: Supabase Dashboard → Settings → API

3. **RESEND_API_KEY** - API key for Resend email service
   - Get from: https://resend.com/api-keys

4. **EMAIL_FROM** - Sender email address (e.g., "Øditr <noreply@yourdomain.com>")
   - Must be verified in Resend dashboard

5. **SITE_URL** - Your website URL for referral links
   - Used in confirmation emails (e.g., `https://yoursite.com`)

## Backend Changes

### Key Updates
- Replaced MongoDB client with Supabase Python client
- Updated all database operations to use Supabase queries
- Maintained all existing API endpoints and logic
- Email confirmation remains the same (Resend)

### API Endpoints (unchanged)
- `POST /api/waitlist` - Join the waitlist (with optional referral code)
- `GET /api/waitlist/count` - Get total waitlist count
- `GET /api/waitlist/code/{code}` - Get user info by referral code
- `GET /api/admin/signups` - List all signups (admin only)

### Position Calculation
Position is calculated dynamically based on:
1. Number of referrals (higher = better position)
2. Sign-up time for users with same referral count (earlier = better)

## How It Works

### When User Joins Waitlist
1. User submits email via frontend
2. Backend checks if email already exists in Supabase
3. If new:
   - Generates unique referral code
   - Stores entry in `waitlist` table
   - Sends confirmation email via Resend with referral link
4. If duplicate:
   - Returns existing entry with current position

### When User Shares Referral Code
1. New user joins with `?ref={code}` parameter
2. Backend validates referral code exists
3. Increments `referral_count` for referrer
4. Stores `referred_by` in new user's record
5. Sends confirmation to new user

### Position Update
- Position is recalculated on every API call based on:
  - Total entries before this user
  - Users with more referrals
  - Users with same referrals joined earlier

## Testing the Integration

### 1. Test Waitlist Signup
```bash
curl -X POST http://localhost:8000/api/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

### 2. Test Referral
```bash
curl -X POST http://localhost:8000/api/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email": "friend@example.com", "ref": "ABC123XY"}'
```

### 3. Get Waitlist Count
```bash
curl http://localhost:8000/api/waitlist/count
```

### 4. Get User by Referral Code
```bash
curl http://localhost:8000/api/waitlist/code/ABC123XY
```

## Email Confirmation Template

Users receive a professional HTML email that includes:
- Their position in the waitlist
- A referral link with their unique code
- Instructions to share and move up the list

The email is sent asynchronously (non-blocking) and failures are logged but don't interrupt the signup flow.

## Migration Notes

- MongoDB collections have been fully replaced with Supabase PostgreSQL
- All existing data from MongoDB should be migrated separately if needed
- The new schema supports all previous functionality
- Referral system is fully preserved and enhanced

## Monitoring

Check backend logs for:
- Supabase connection issues: "Database connection failed"
- Email sending failures: "Email send failed (non-fatal)"
- Referral code generation: "Confirmation email sent to..."

## Support

For issues:
1. Verify all environment variables are set in Vercel project settings
2. Check Supabase dashboard for table creation and data
3. Verify Resend API key is valid and has verified sender email
4. Check backend logs for specific error messages
