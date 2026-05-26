import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";

// Delete one generated batch: remove its files from Storage and the DB row.
export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

  // RLS ensures the row (if any) belongs to this user.
  const { data: row } = await supabase
    .from("quotations")
    .select("id, results")
    .eq("id", id)
    .single();
  if (!row) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const paths: string[] = [];
  for (const r of (row.results as { docx_path?: string; pdf_path?: string }[]) || []) {
    if (r.docx_path) paths.push(r.docx_path);
    if (r.pdf_path) paths.push(r.pdf_path);
  }

  const admin = createAdminClient();
  if (paths.length) await admin.storage.from("outputs").remove(paths);

  const { error } = await supabase.from("quotations").delete().eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ ok: true });
}
