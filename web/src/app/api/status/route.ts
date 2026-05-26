import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Reports doc-gen capabilities (AI availability, PDF engine) to the UI.
export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

  try {
    const r = await fetch(`${process.env.DOCGEN_URL}/health`, {
      headers: { "X-Docgen-Secret": process.env.DOCGEN_SECRET ?? "" },
      cache: "no-store",
    });
    return NextResponse.json(await r.json());
  } catch {
    return NextResponse.json(
      { ok: false, ai_available: false, pdf_engine: "none", error: "doc-gen unreachable" },
      { status: 200 },
    );
  }
}
