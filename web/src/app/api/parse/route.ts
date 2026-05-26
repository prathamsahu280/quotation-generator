import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Parse pasted quotation text into structured fields (rule-based or Gemini),
// by proxying to the Python doc-gen service. Auth-gated.
export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

  const { text, ai_mode } = await req.json();
  if (!text || !text.trim()) {
    return NextResponse.json({ error: "Nothing to parse." }, { status: 400 });
  }

  try {
    const r = await fetch(`${process.env.DOCGEN_URL}/parse`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Docgen-Secret": process.env.DOCGEN_SECRET ?? "",
      },
      body: JSON.stringify({ text, ai_mode: !!ai_mode }),
    });
    const body = await r.json();
    if (!r.ok) {
      return NextResponse.json({ error: body.detail || "Parse failed." }, { status: 502 });
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json(
      { error: "Doc-gen service unreachable. Is it running on DOCGEN_URL?" },
      { status: 502 },
    );
  }
}
