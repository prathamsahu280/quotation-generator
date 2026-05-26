import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export const maxDuration = 60; // PDF->DOCX conversion can take a few seconds

const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function companyFromFilename(name: string): string {
  let stem = name.replace(/\.[^.]+$/, "");
  stem = stem.replace(/[_\s-]*letter[_\s-]*head/gi, " ");
  stem = stem.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return stem.toUpperCase() || "COMPANY";
}

// Upload a letterhead. Accepts .docx (stored as-is) or .pdf (converted to .docx
// by the doc-gen service). Stores the file in the user's Storage folder and
// records a row. .docx could be uploaded directly from the browser, but routing
// everything here keeps PDF conversion server-side and the flow uniform.
export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file uploaded." }, { status: 400 });
  }

  const name = file.name || "letterhead";
  const ext = name.toLowerCase().slice(name.lastIndexOf("."));
  if (ext !== ".docx" && ext !== ".pdf") {
    return NextResponse.json({ error: "Only .docx or .pdf letterheads are supported." }, { status: 400 });
  }

  let docxBytes = Buffer.from(await file.arrayBuffer());

  if (ext === ".pdf") {
    try {
      const r = await fetch(`${process.env.DOCGEN_URL}/convert`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Docgen-Secret": process.env.DOCGEN_SECRET ?? "",
        },
        body: JSON.stringify({ filename: name, content_b64: docxBytes.toString("base64") }),
      });
      const body = await r.json();
      if (!r.ok) {
        return NextResponse.json({ error: body.detail || "PDF conversion failed." }, { status: 400 });
      }
      docxBytes = Buffer.from(body.docx_b64, "base64");
    } catch {
      return NextResponse.json(
        { error: "Doc-gen service unreachable for PDF conversion." },
        { status: 502 },
      );
    }
  }

  const id = crypto.randomUUID();
  const path = `${user.id}/${id}.docx`;

  const { error: upErr } = await supabase.storage
    .from("letterheads")
    .upload(path, docxBytes, { contentType: DOCX_MIME });
  if (upErr) return NextResponse.json({ error: upErr.message }, { status: 500 });

  const row = {
    id,
    user_id: user.id,
    company: companyFromFilename(name),
    original_name: name,
    storage_path: path,
  };
  const { error: dbErr } = await supabase.from("letterheads").insert(row);
  if (dbErr) {
    await supabase.storage.from("letterheads").remove([path]); // roll back the file
    return NextResponse.json({ error: dbErr.message }, { status: 500 });
  }

  return NextResponse.json({ letterhead: { ...row, created_at: new Date().toISOString() } });
}
