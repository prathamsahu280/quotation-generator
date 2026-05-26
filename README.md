# Quotation Generator — Supabase + Next.js

A scalable multi-tenant web app. Each user signs in, uploads their own company
**letterheads**, pastes the quote details, and generates several quotations —
each on a different letterhead, each with a **different look and wording**.
Output is **PDF + editable DOCX**. Optional **AI mode** (Google Gemini) parses
messy input and writes the quotation prose; it falls back to a rule-based engine
when AI is off or unavailable.

## Architecture

```
Browser ──► Supabase           (Auth · Postgres w/ RLS · Storage)   ◄── direct, per-user
   │
   └──► Next.js route handlers (server)
            /api/parse     → doc-gen /parse
            /api/generate  → fetch letterhead from Storage → doc-gen /generate
                             → upload PDFs/DOCX to Storage → record row
                                   │
                                   ▼
            Python doc-gen service (FastAPI)  ── renders onto .docx, makes PDF,
                                                 runs Gemini parse/draft
```

- **`web/`** — Next.js 16 (App Router, TypeScript, Tailwind). Auth/DB/Storage via
  Supabase; orchestration + AI proxying in server route handlers. The Gemini and
  Supabase service-role keys never reach the browser.
- **`docgen/`** — stateless Python FastAPI service. The only place that touches
  `python-docx` / LibreOffice / Word and the Gemini SDK. Letterhead bytes in,
  rendered DOCX/PDF (base64) out. Protected by a shared secret.
- **`supabase/schema.sql`** — tables, RLS policies, and Storage buckets.

> Two earlier single-server versions live in `app/` (FastAPI + SQLite) and
> `quotation-generator/` (Claude Code plugin). They're superseded by this stack
> but left in place; ignore them for the Supabase deployment.

## Setup

### 1. Supabase
1. Create a project at <https://supabase.com>.
2. **SQL Editor → New query →** paste `supabase/schema.sql` → **Run**. This
   creates the `letterheads` / `quotations` tables (with row-level security) and
   the private `letterheads` / `outputs` Storage buckets.
3. **Project Settings → API**: copy the **Project URL**, the **publishable** key,
   and the **secret** (service-role) key.
4. (For quick local testing) **Authentication → Providers → Email**: you can turn
   off "Confirm email" so new signups can log in immediately.

### 2. Doc-gen service (`docgen/`)
```
cd docgen
python -m pip install -r requirements.txt        # add --user on locked machines
cp .env.example .env                              # set DOCGEN_SECRET + GEMINI_API_KEY
python -m uvicorn main:app --port 8500
```
PDF output needs **LibreOffice** (any OS, auto-detected) or **MS Word**
(`docx2pdf`); without either, output is DOCX only. **PDF letterhead uploads also
require LibreOffice** (Draw) to rasterise the page — Writer alone is not enough.
If `soffice` isn't on `PATH`, set `SOFFICE_BIN` to its full path.

### 3. Web app (`web/`)
```
cd web
npm install
cp .env.local.example .env.local                 # fill in Supabase URL + keys + DOCGEN_*
npm run dev                                       # http://localhost:3000
```

`web/.env.local`:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | your `https://<ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the **publishable** key (browser-safe) |
| `SUPABASE_SERVICE_ROLE_KEY` | the **secret** key (server only) |
| `DOCGEN_URL` | `http://127.0.0.1:8500` locally |
| `DOCGEN_SECRET` | must match `docgen/.env` |

## Deploying

- **Web** → Vercel (set the same env vars). 
- **Doc-gen** → any container host (Render / Railway / Fly / KVM). Install
  LibreOffice in the image (`apt-get install -y libreoffice`, or the slimmer
  `libreoffice-writer libreoffice-draw`) — Writer renders DOCX→PDF and Draw
  rasterises PDF letterhead uploads. Set `DOCGEN_SECRET` and `GEMINI_API_KEY`,
  point the web app's `DOCGEN_URL` at it, and set `SOFFICE_BIN` if `soffice`
  isn't on `PATH`.
- **Supabase** is already managed/scalable.

## Notes
- Letterhead uploads accept **.docx** and **.pdf**. PDFs are converted to an
  editable .docx server-side by the doc-gen `/convert` endpoint on upload.
- Generated download links are 7-day signed URLs from private Storage buckets.
