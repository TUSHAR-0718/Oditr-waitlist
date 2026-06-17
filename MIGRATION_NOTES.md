# MongoDB to Supabase Migration

## Summary of Changes

This document outlines all changes made to migrate your waitlist backend from MongoDB to Supabase PostgreSQL.

## Files Modified

### 1. `/backend/server.py`

**Removed:**
- `motor` AsyncIOMotorClient (MongoDB async driver)
- IPv4 monkeypatch for MongoDB Atlas
- certifi usage for MongoDB TLS
- `db` MongoDB client instance
- MongoDB shutdown event

**Added:**
- Supabase client initialization using `create_client(SUPABASE_URL, SUPABASE_ANON_KEY)`

**Updated Functions:**

#### `unique_ref_code()`
- **Before:** Used `await db.waitlist.find_one({"referral_code": code})`
- **After:** Uses `supabase.table("waitlist").select("id").eq("referral_code", code).execute()`

#### `compute_position(entry)`
- **Before:** Used `$gt` and `$lt` MongoDB operators
- **After:** Uses Supabase query methods: `.gt()`, `.lt()`, `.eq()` with `count="exact"`

#### `join_waitlist()`
- **Before:** Used `await db.waitlist.find_one()` and `await db.waitlist.insert_one()`
- **After:** Uses Supabase `.select()`, `.insert()`, `.update()` methods
- **Before:** Used `await db.waitlist.update_one()` with `$inc` operator
- **After:** Fetches current count and increments manually: `current_count + 1`

#### `waitlist_count()`
- **Before:** Used `await db.waitlist.count_documents({})`
- **After:** Uses `supabase.table("waitlist").select("id", count="exact").execute()`

#### `waitlist_by_code(code)`
- **Before:** Used `await db.waitlist.find_one()`
- **After:** Uses `supabase.table("waitlist").select("*").eq("referral_code", code).execute()`

#### `list_signups()`
- **Before:** Used MongoDB cursor with `.sort()`, `.skip()`, `.limit()`
- **After:** Uses Supabase `.order()`, `.range()` methods

#### `backfill_waitlist()`
- **Before:** Used MongoDB update operators `$exists`, `$set`, `$inc`
- **After:** Uses Supabase `.is_()` method to check for NULL values and `.update()` to set them
- Removed fields that don't exist in PostgreSQL schema

### 2. `/backend/requirements.txt`

**Removed:**
- `pymongo==4.5.0`
- `motor==3.3.1`
- `certifi` (no longer needed)

**Added:**
- `supabase>=2.0.0`

**Kept:**
- All other dependencies unchanged (including `resend` for email)

### 3. `/backend/email_service.py`

**No changes required** - Already configured to use Resend with environment variables.

## Key Differences in Query Patterns

### Finding Records
```python
# MongoDB
existing = await db.waitlist.find_one({"email": email_normalized})

# Supabase
response = supabase.table("waitlist").select("*").eq("email", email_normalized).execute()
existing = response.data[0] if response.data else None
```

### Counting Records
```python
# MongoDB
count = await db.waitlist.count_documents({})

# Supabase
response = supabase.table("waitlist").select("id", count="exact").execute()
count = response.count or 0
```

### Inserting Records
```python
# MongoDB
await db.waitlist.insert_one(entry)

# Supabase
supabase.table("waitlist").insert(entry).execute()
```

### Updating Records
```python
# MongoDB
await db.waitlist.update_one({"id": entry_id}, {"$set": {"field": value}})

# Supabase
supabase.table("waitlist").update({"field": value}).eq("id", entry_id).execute()
```

### Incrementing Values
```python
# MongoDB
await db.waitlist.update_one({"id": id}, {"$inc": {"referral_count": 1}})

# Supabase
current = supabase.table("waitlist").select("referral_count").eq("id", id).execute()
new_count = (current.data[0]["referral_count"] or 0) + 1
supabase.table("waitlist").update({"referral_count": new_count}).eq("id", id).execute()
```

## Environment Variables

### Removed
- `MONGO_URL` - No longer needed
- `DB_NAME` - MongoDB database name

### Added
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anonymous key

### Unchanged (still required)
- `RESEND_API_KEY` - Email API key
- `EMAIL_FROM` - Sender email
- `SITE_URL` - Application URL for referral links

## Data Migration

If you have existing data in MongoDB, you'll need to migrate it to Supabase:

1. Export data from MongoDB as JSON
2. Transform to match Supabase schema
3. Import via Supabase dashboard or API

Example transformation:
```python
# MongoDB document
{
  "_id": ObjectId(...),
  "id": "uuid-string",
  "email": "user@example.com",
  "referral_code": "ABC123XY",
  "referral_count": 5,
  "referred_by": "XYZ789AB",
  "created_at": "2024-06-17T10:00:00Z"
}

# Supabase row (same structure, no _id field)
{
  "id": "uuid-string",
  "email": "user@example.com",
  "referral_code": "ABC123XY",
  "referral_count": 5,
  "referred_by": "XYZ789AB",
  "created_at": "2024-06-17T10:00:00Z"
}
```

## Testing Checklist

- [ ] Environment variables set in Vercel project
- [ ] Supabase table created with correct schema
- [ ] Backend can connect to Supabase (no connection errors)
- [ ] New user can join waitlist
- [ ] Confirmation email is sent via Resend
- [ ] Referral links work correctly
- [ ] Position calculation is accurate
- [ ] Admin can view signups
- [ ] Referral count increments when referred user joins

## Rollback Plan

If issues occur:
1. Keep MongoDB running in parallel
2. Revert to MongoDB version of server.py
3. Restore `motor` and `pymongo` to requirements.txt
4. Investigate Supabase issues and retry

## Performance Notes

- Supabase queries are generally faster than MongoDB for simple operations
- Pagination is handled with `.range()` instead of cursor-based iteration
- Count operations use `count="exact"` for accuracy
- No significant performance changes expected for current volume

## Future Improvements

1. Add Row-Level Security (RLS) policies if authentication is added
2. Implement automatic position cache for faster lookups
3. Add database triggers for automatic `updated_at` timestamps
4. Consider materialized views for admin dashboard queries
