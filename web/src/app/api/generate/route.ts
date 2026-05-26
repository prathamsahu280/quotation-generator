import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";

export const maxDuration = 120; // rendering + PDF can take a while

const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function slug(s: string, n = 14) {
  return (
    (s || "")
      .replace(/[^A-Za-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase()
      .slice(0, n) || "quote"
  );
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

  const bodyIn = await req.json();
  const { data, count, ai_mode, make_pdf, seed } = bodyIn;
  const letterheadIds: string[] = bodyIn.letterhead_ids || [];

  // Load the user's letterheads (RLS ensures these belong to them).
  let query = supabase.from("letterheads").select("*").eq("user_id", user.id);
  if (letterheadIds.length) query = query.in("id", letterheadIds);
  const { data: rows, error: lhErr } = await query;
  if (lhErr) return NextResponse.json({ error: lhErr.message }, { status: 500 });
  if (!rows || rows.length === 0) {
    return NextResponse.json({ error: "No letterheads available." }, { status: 400 });
  }

  const admin = createAdminClient();

  // Download each selected letterhead from storage and base64-encode it.
  const letterheads: { company: string; filename: string; content_b64: string }[] = [];
  for (const lh of rows) {
    const { data: blob, error } = await admin.storage
      .from("letterheads")
      .download(lh.storage_path);
    if (error || !blob) {
      return NextResponse.json(
        { error: `Could not read letterhead "${lh.original_name}".` },
        { status: 500 },
      );
    }
    const buf = Buffer.from(await blob.arrayBuffer());
    letterheads.push({
      company: lh.company,
      filename: lh.original_name,
      content_b64: buf.toString("base64"),
    });
  }

  // Call the Python doc-gen service.
  let gen;
  try {
    const r = await fetch(`${process.env.DOCGEN_URL}/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Docgen-Secret": process.env.DOCGEN_SECRET ?? "",
      },
      body: JSON.stringify({
        data,
        letterheads,
        count: count ?? 3,
        ai_mode: !!ai_mode,
        make_pdf: make_pdf !== false,
        seed: seed ?? null,
      }),
    });
    gen = await r.json();
    if (!r.ok) {
      return NextResponse.json({ error: gen.detail || "Generation failed." }, { status: 502 });
    }
  } catch {
    return NextResponse.json(
      { error: "Doc-gen service unreachable. Is it running on DOCGEN_URL?" },
      { status: 502 },
    );
  }

  // Upload outputs to storage and mint signed download URLs.
  const batchId = crypto.randomUUID();
  const buyerSlug = slug(data.buyer || data.subject);
  const WEEK = 60 * 60 * 24 * 7;
  // What we persist (durable storage paths) vs. what we return now (signed URLs).
  const storedResults = [];
  const responseResults = [];

  for (const res of gen.results) {
    const tag = slug(res.company, 12);
    const stem = `quotation_${buyerSlug}_${tag}_${res.n}`;
    const base = `${user.id}/${batchId}`;

    const docxPath = `${base}/${stem}.docx`;
    await admin.storage
      .from("outputs")
      .upload(docxPath, Buffer.from(res.docx_b64, "base64"), {
        contentType: DOCX_MIME,
        upsert: true,
      });
    const { data: docxSigned } = await admin.storage
      .from("outputs")
      .createSignedUrl(docxPath, WEEK);

    let pdfPath: string | null = null;
    let pdfUrl: string | null = null;
    if (res.pdf_b64) {
      pdfPath = `${base}/${stem}.pdf`;
      await admin.storage
        .from("outputs")
        .upload(pdfPath, Buffer.from(res.pdf_b64, "base64"), {
          contentType: "application/pdf",
          upsert: true,
        });
      const { data: pdfSigned } = await admin.storage
        .from("outputs")
        .createSignedUrl(pdfPath, WEEK);
      pdfUrl = pdfSigned?.signedUrl ?? null;
    }

    const meta = { n: res.n, company: res.company, letterhead: res.letterhead, summary: res.summary };
    storedResults.push({ ...meta, docx_path: docxPath, pdf_path: pdfPath });
    responseResults.push({ ...meta, docx_url: docxSigned?.signedUrl ?? null, pdf_url: pdfUrl });
  }

  // Record the batch (RLS: user_id must equal auth.uid()). We store storage
  // paths, not signed URLs, so the History page can mint fresh links any time.
  await supabase.from("quotations").insert({
    id: batchId,
    user_id: user.id,
    buyer: (data.buyer || "").slice(0, 255),
    subject: (data.subject || "").slice(0, 500),
    ai_used: gen.ai_used,
    results: storedResults,
  });

  return NextResponse.json({ results: responseResults, errors: gen.errors ?? [], ai_used: gen.ai_used });
}
