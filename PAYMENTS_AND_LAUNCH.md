# KaziLink launch plan

## 1. Put the MVP online
The included `Dockerfile` and `render.yaml` are ready for a cloud deployment.
For the first public test, use a cloud host and a hosted Postgres database.

Supabase is a practical database/auth option. Its current Free plan includes a Postgres database, Auth, 1 GB storage and Realtime quotas, so it can be used for an early test. Free projects can pause after inactivity. See the official pricing page before launch.

## 2. Move SQLite to Supabase
`supabase_schema.sql` contains the production database starting point.
Do not put a Supabase service-role key into the browser. Keep privileged keys on the server.

## 3. Mobile Money
The app currently records the marketplace/plan structure but does NOT pretend to process real money.
Before charging customers, connect a licensed payment provider for:
- MTN Mobile Money Uganda
- Airtel Money Uganda

The payment flow should be:
1. User selects Featured/Premium/Business.
2. Server creates a pending payment.
3. Provider requests/collects payment.
4. Provider callback/webhook is verified by the server.
5. KaziLink activates the plan only after verified payment.
6. Every transaction is stored with amount, reference, status and timestamps.

Never ask users to send money to a personal number from inside the app.

## 4. Notifications
Add:
- New job notification to matching workers
- New application notification to customers
- Application accepted/rejected notification
- Verification result notification
- Payment confirmation

For Android, Firebase Cloud Messaging is a suitable next step.

## 5. Android
The current KaziLink is a PWA and can be installed from a supported Android browser.
For a Play Store APK/AAB, package the web app with a maintained Android wrapper such as Capacitor after the cloud backend is live.

## 6. Production security checklist
Before public launch:
- HTTPS only
- Real OTP verification
- Supabase Row Level Security
- Server-side authorization for admin actions
- Rate limiting
- Abuse/report system
- Image upload restrictions
- Privacy policy and terms
- Backups
- Error monitoring
- Remove demo admin credentials
- Never expose service-role/API secrets in frontend code

## Current status
DONE:
- Full runnable MVP
- Database-backed local accounts/jobs/applications/reviews
- Admin verification
- PWA install files
- Docker deployment files
- Supabase migration schema
- Payment architecture plan

NOT YET LIVE:
- Public hosting
- Production Supabase connection
- Real MTN/Airtel payment credentials
- Push notification credentials
- Play Store release

Those last items require accounts/credentials owned by the app operator; they should not be invented or embedded in the project.
