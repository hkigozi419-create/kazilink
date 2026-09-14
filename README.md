# KaziLink Real MVP

This is a runnable full-stack MVP foundation for KaziLink.

## What works now
- Customer and worker registration
- Secure password hashing (PBKDF2)
- Login/logout sessions
- SQLite database persistence
- Worker profiles and trade/location search
- Customer job posting
- Worker job applications
- Reviews and worker ratings
- Admin dashboard
- Worker verification controls
- WhatsApp contact buttons
- Demo seed workers

## Start
Requires Python 3.9+.

### Windows
Open Command Prompt in this folder:
    python kazilink_server.py

### Linux / macOS / Termux
    python3 kazilink_server.py

Then open:
    http://127.0.0.1:8080

The database `kazilink.db` is created automatically.

## Demo accounts
Worker:
- phone: +256700000001
- password: Demo123!

Admin:
- email: admin@kazilink.local
- password: KaziLink123!

IMPORTANT: change the admin password before any public deployment. You can set:
KAZILINK_ADMIN_EMAIL
KAZILINK_ADMIN_PASSWORD

## Important production work still needed
This is a real runnable backend MVP, but it is not yet a public Play Store app.
Before launch we should add:
- Cloud hosting + HTTPS
- Persistent production session storage
- SMS/OTP phone verification
- ID/document verification upload
- Image/file uploads
- Push notifications
- Real-time messaging
- MTN/Airtel Mobile Money payments
- Paid worker plans and featured listings
- Stronger admin moderation/audit logs
- Privacy policy, terms, abuse reporting
- Android/iOS packaging and Play Store release

The current architecture deliberately keeps the first version simple so these can be added without rebuilding the core marketplace.


## Supabase connection added
This package includes `public/supabase-config.js` with the Supabase Project URL and
publishable browser key, plus `supabase_rls_policies.sql` for the starter read policies.
The Supabase secret key is intentionally not included.

After running the RLS policy SQL in Supabase, opening the app should show
“Supabase connected” when the browser can reach the project.


## KaziLink live data mode
The browser now includes `public/kazilink-live.js`. When the Supabase connection is available, worker search reads worker/user data from Supabase using the publishable key and the RLS read policies. If Supabase is unavailable, the app falls back to its local MVP API.
