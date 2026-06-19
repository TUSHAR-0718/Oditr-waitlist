# Øditr Waitlist - Setup & Debugging Guide

## Frontend & Backend Integration

### What Was Fixed

1. **WebSocket Errors** - Updated craco config to use proper WebSocket URL for HMR (Hot Module Replacement)
2. **Blob URL Errors** - Disabled problematic source maps for workers in development
3. **CORS Issues** - Added CORS headers and API proxy configuration
4. **Source Maps** - Set proper devtool configuration to avoid blob:// URL malformations

### Error Messages Fixed

- ❌ `[Error] Not allowed to load local resource: blob://nullhttps//...` → FIXED
- ❌ `[Error] WebSocket connection to 'wss://...:3000/ws' failed` → FIXED
- ✅ All frontend errors resolved

---

## Running Locally

### Step 1: Start the Backend

```bash
cd backend
python3 -m pip install --break-system-packages -q -r requirements.txt
set -a && source /vercel/share/v0-project/.env.development.local && set +a
python3 -m uvicorn server:app --port 8000
```

The backend will be available at: `http://localhost:8000`

### Step 2: Start the Frontend

In a new terminal:

```bash
cd frontend
yarn dev  # or npm start
```

The frontend will be available at: `http://localhost:3000`

---

## Environment Variables

### Backend (.env in backend folder or .env.development.local in root)

```
SUPABASE_URL=https://dxjnpodeuzpthgmpcquy.supabase.co
SUPABASE_ANON_KEY=your-anon-key
RESEND_API_KEY=your-resend-key
EMAIL_FROM=noreply@oditr.app
SITE_URL=http://localhost:3000
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=admin
```

### Frontend (frontend/.env.development.local)

```
REACT_APP_BACKEND_URL=http://localhost:8000
```

---

## Debugging

### Check if Backend is Running

```bash
curl http://localhost:8000/api/
```

Expected response: Should show API info or 200 OK

### Check Waitlist Count

```bash
curl http://localhost:8000/api/waitlist/count
```

Expected response: `{"count": 1500}`

### Test Email Submission

```bash
curl -X POST http://localhost:8000/api/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

### Frontend Console Logs

When you submit the form, check the browser console (F12) for:

```
[v0] Submitting email: test@example.com
[v0] API endpoint: http://localhost:8000/api
[v0] Success response: {...}
```

If you see errors, they'll be logged with `[v0]` prefix.

---

## Supabase Database

### Current Schema

```sql
CREATE TABLE public.waitlist (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  referral_code TEXT UNIQUE NOT NULL,
  referral_count INT DEFAULT 0,
  referred_by TEXT,
  created_at TIMESTAMP WITH TIME ZONE,
  updated_at TIMESTAMP WITH TIME ZONE
);
```

### Query Examples

**Get all waitlisters:**
```sql
SELECT email, created_at, referral_count FROM public.waitlist 
ORDER BY created_at DESC;
```

**Get count:**
```sql
SELECT COUNT(*) as total FROM public.waitlist;
```

**Find by email:**
```sql
SELECT * FROM public.waitlist WHERE email = 'user@example.com';
```

---

## Resend Email Integration

### Current Setup

- **API Key**: Configured in environment
- **Sender Email**: Configured as `EMAIL_FROM`
- **Template**: Simple HTML with position and referral link
- **Delivery**: Automatic on waitlist signup

### Email Contents

The confirmation email includes:
- User's position in the waitlist
- Unique referral code
- Link to share with friends
- Link back to the site

### Testing Emails

1. Submit an email via the frontend form
2. Check Resend dashboard for delivery status
3. Verify email content in inbox

---

## Common Issues & Solutions

### Issue: "Unable to connect to the server"

**Causes:**
- Backend not running on port 8000
- REACT_APP_BACKEND_URL not set
- Firewall blocking port 8000

**Solution:**
```bash
# Terminal 1: Backend
cd backend
set -a && source /vercel/share/v0-project/.env.development.local && set +a
python3 -m uvicorn server:app --port 8000

# Terminal 2: Frontend  
cd frontend
yarn dev
```

### Issue: "Please enter a valid email"

**Causes:**
- Email format validation issue
- Backend validation error (422 status)

**Solution:**
- Use proper email format: `user@example.com`
- Check backend logs for validation details

### Issue: "You're already on the waitlist"

**Expected behavior** - User already has an entry in database
- Return existing position
- Don't duplicate the entry

### Issue: Frontend not connecting to backend

**Check:**
1. Backend URL in console logs matches `REACT_APP_BACKEND_URL`
2. Backend is running and responding to requests
3. CORS headers are properly set (done via craco config)
4. Proxy configuration is active (checked in dev server output)

---

## Monitoring

### Backend Logs

Look for these patterns:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Frontend Logs

Look for these patterns in browser console:
```
[v0] API endpoint: http://localhost:8000/api
[v0] Success response: {position: 42, ...}
```

### Email Delivery

Monitor in Resend dashboard:
- Emails sent: Count should increase
- Delivery status: Should show "delivered" or "opened"
- Bounce rate: Should be 0%

---

## Production Deployment

### Backend (Vercel)

1. Connect GitHub repo to Vercel
2. Set environment variables:
   - SUPABASE_URL
   - SUPABASE_ANON_KEY
   - RESEND_API_KEY
   - EMAIL_FROM
   - SITE_URL (production domain)
3. Deploy Python backend service

### Frontend (Vercel)

1. Set REACT_APP_BACKEND_URL to production backend URL
2. Deploy frontend to Vercel
3. Update SITE_URL in backend env vars

---

## Next Steps

1. ✅ Start both servers locally
2. ✅ Test form submission with a test email
3. ✅ Verify email delivery via Resend
4. ✅ Check Supabase for new database entries
5. ✅ Deploy to Vercel when ready
