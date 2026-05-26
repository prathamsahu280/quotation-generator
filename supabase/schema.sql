-- =====================================================================
-- Quotation Generator — Supabase schema (tables, RLS, storage buckets)
-- Paste into: Supabase Dashboard -> SQL Editor -> New query -> Run.
-- Safe to re-run (idempotent).
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- letterheads: one row per uploaded blank letterhead. The file itself
-- lives in the "letterheads" storage bucket at storage_path.
-- ---------------------------------------------------------------------
create table if not exists public.letterheads (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users (id) on delete cascade,
  company       text not null default '',
  original_name text not null default '',
  storage_path  text not null,
  created_at    timestamptz not null default now()
);
create index if not exists letterheads_user_id_idx on public.letterheads (user_id);
alter table public.letterheads enable row level security;

drop policy if exists "letterheads_select_own" on public.letterheads;
drop policy if exists "letterheads_insert_own" on public.letterheads;
drop policy if exists "letterheads_update_own" on public.letterheads;
drop policy if exists "letterheads_delete_own" on public.letterheads;
create policy "letterheads_select_own" on public.letterheads
  for select to authenticated using (auth.uid() = user_id);
create policy "letterheads_insert_own" on public.letterheads
  for insert to authenticated with check (auth.uid() = user_id);
create policy "letterheads_update_own" on public.letterheads
  for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "letterheads_delete_own" on public.letterheads
  for delete to authenticated using (auth.uid() = user_id);

-- ---------------------------------------------------------------------
-- quotations: one row per generation batch. results = JSON array of
-- {n, company, letterhead, summary, docx_path, pdf_path}.
-- ---------------------------------------------------------------------
create table if not exists public.quotations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  buyer       text not null default '',
  subject     text not null default '',
  ai_used     boolean not null default false,
  results     jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists quotations_user_id_idx on public.quotations (user_id);
alter table public.quotations enable row level security;

drop policy if exists "quotations_select_own" on public.quotations;
drop policy if exists "quotations_insert_own" on public.quotations;
drop policy if exists "quotations_delete_own" on public.quotations;
create policy "quotations_select_own" on public.quotations
  for select to authenticated using (auth.uid() = user_id);
create policy "quotations_insert_own" on public.quotations
  for insert to authenticated with check (auth.uid() = user_id);
create policy "quotations_delete_own" on public.quotations
  for delete to authenticated using (auth.uid() = user_id);

-- ---------------------------------------------------------------------
-- Storage buckets (private). Object paths are "{user_id}/...":
--   letterheads/{user_id}/{uuid}.docx
--   outputs/{user_id}/{quotation_id}/{file}
-- ---------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('letterheads', 'letterheads', false),
       ('outputs',     'outputs',     false)
on conflict (id) do nothing;

-- Letterheads bucket: users manage only objects under their own uid folder.
drop policy if exists "lh_obj_select_own" on storage.objects;
drop policy if exists "lh_obj_insert_own" on storage.objects;
drop policy if exists "lh_obj_update_own" on storage.objects;
drop policy if exists "lh_obj_delete_own" on storage.objects;
create policy "lh_obj_select_own" on storage.objects
  for select to authenticated
  using (bucket_id = 'letterheads' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "lh_obj_insert_own" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'letterheads' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "lh_obj_update_own" on storage.objects
  for update to authenticated
  using (bucket_id = 'letterheads' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "lh_obj_delete_own" on storage.objects
  for delete to authenticated
  using (bucket_id = 'letterheads' and (storage.foldername(name))[1] = auth.uid()::text);

-- Outputs bucket: users can READ their own generated files. Writes are done
-- by the Next.js server with the service-role key (which bypasses RLS).
drop policy if exists "out_obj_select_own" on storage.objects;
create policy "out_obj_select_own" on storage.objects
  for select to authenticated
  using (bucket_id = 'outputs' and (storage.foldername(name))[1] = auth.uid()::text);
