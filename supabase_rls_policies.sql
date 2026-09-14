-- KaziLink: starter RLS policies for browser/public access.
-- Run this in Supabase SQL Editor AFTER the tables already exist.
-- These policies allow public read access to worker profiles and basic worker users.
-- Job/application/review writes should continue through the server/backend.

alter table public.users enable row level security;
alter table public.worker_profiles enable row level security;
alter table public.jobs enable row level security;
alter table public.applications enable row level security;
alter table public.reviews enable row level security;

drop policy if exists "Public can view worker users" on public.users;
create policy "Public can view worker users"
on public.users for select
to anon, authenticated
using (role = 'worker');

drop policy if exists "Public can view worker profiles" on public.worker_profiles;
create policy "Public can view worker profiles"
on public.worker_profiles for select
to anon, authenticated
using (true);

drop policy if exists "Public can view open jobs" on public.jobs;
create policy "Public can view open jobs"
on public.jobs for select
to anon, authenticated
using (status = 'open');
