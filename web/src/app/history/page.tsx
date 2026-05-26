import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import HistoryList, { type Batch } from "@/components/HistoryList";

export const dynamic = "force-dynamic";

type StoredResult = {
  n: number;
  company: string;
  letterhead: string;
  summary: string;
  docx_path?: string | null;
  pdf_path?: string | null;
};

export default async function HistoryPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const { data: rows } = await supabase
    .from("quotations")
    .select("*")
    .order("created_at", { ascending: false });

  const admin = createAdminClient();
  const HOUR = 60 * 60;

  const batches: Batch[] = [];
  for (const row of rows ?? []) {
    const results = [];
    for (const r of (row.results as StoredResult[]) ?? []) {
      let docx_url: string | null = null;
      let pdf_url: string | null = null;
      if (r.docx_path) {
        const { data } = await admin.storage.from("outputs").createSignedUrl(r.docx_path, HOUR);
        docx_url = data?.signedUrl ?? null;
      }
      if (r.pdf_path) {
        const { data } = await admin.storage.from("outputs").createSignedUrl(r.pdf_path, HOUR);
        pdf_url = data?.signedUrl ?? null;
      }
      results.push({
        n: r.n,
        company: r.company,
        letterhead: r.letterhead,
        summary: r.summary,
        docx_url,
        pdf_url,
      });
    }
    batches.push({
      id: row.id,
      buyer: row.buyer,
      subject: row.subject,
      ai_used: row.ai_used,
      created_at: row.created_at,
      results,
    });
  }

  return <HistoryList batches={batches} email={user.email ?? ""} />;
}
