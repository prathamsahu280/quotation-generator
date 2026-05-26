"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { downloadUrl, fileBase } from "@/lib/download";

export type Batch = {
  id: string;
  buyer: string;
  subject: string;
  ai_used: boolean;
  created_at: string;
  results: {
    n: number;
    company: string;
    letterhead: string;
    summary: string;
    docx_url: string | null;
    pdf_url: string | null;
  }[];
};

export default function HistoryList({ batches, email }: { batches: Batch[]; email: string }) {
  const router = useRouter();
  const supabase = createClient();
  const [items, setItems] = useState<Batch[]>(batches);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function logout() {
    await supabase.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  async function remove(id: string) {
    if (!confirm("Delete this quotation batch and its files permanently?")) return;
    setDeleting(id);
    const r = await fetch(`/api/quotations/${id}`, { method: "DELETE" });
    setDeleting(null);
    if (r.ok) setItems((prev) => prev.filter((b) => b.id !== id));
    else alert("Delete failed. Please try again.");
  }

  const viewBtn =
    "rounded-md border border-indigo-500 px-3 py-1 text-sm text-indigo-600 hover:bg-indigo-600 hover:text-white";
  const dlBtn =
    "rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-indigo-500 hover:text-indigo-600";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-6 py-3">
          <span className="font-bold text-indigo-700">Quotation Generator</span>
          <Link href="/" className="text-sm text-slate-500 hover:text-indigo-600">
            ← New quotation
          </Link>
          <span className="flex-1" />
          <span className="hidden text-sm text-slate-500 sm:inline">{email}</span>
          <button
            onClick={logout}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:border-indigo-500"
          >
            Log out
          </button>
        </div>
      </div>

      <main className="mx-auto max-w-4xl px-6 py-6">
        <h1 className="text-2xl font-bold">History</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every batch you&apos;ve generated. Open or download the files, or delete a batch.
        </p>

        {items.length === 0 && (
          <p className="mt-8 rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-400">
            No quotations yet.{" "}
            <Link href="/" className="text-indigo-600">
              Generate your first one →
            </Link>
          </p>
        )}

        <div className="mt-4 space-y-4">
          {items.map((b) => (
            <section key={b.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-semibold">{b.subject || "(no subject)"}</h2>
                  <p className="mt-0.5 text-sm text-slate-500">
                    {b.buyer ? `${b.buyer} · ` : ""}
                    {new Date(b.created_at).toLocaleString()} · {b.results.length} quotation
                    {b.results.length === 1 ? "" : "s"}
                    {b.ai_used && (
                      <span className="ml-2 rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                        AI
                      </span>
                    )}
                  </p>
                </div>
                <button
                  onClick={() => remove(b.id)}
                  disabled={deleting === b.id}
                  className="rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-600 hover:bg-red-600 hover:text-white disabled:opacity-50"
                >
                  {deleting === b.id ? "Deleting…" : "Delete"}
                </button>
              </div>

              <ul className="mt-3 divide-y divide-slate-100">
                {b.results.map((r) => (
                  <li key={r.n} className="flex flex-wrap items-center gap-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">
                        #{r.n} · {r.company}
                      </div>
                      <div className="truncate text-xs text-slate-400">
                        {r.summary} | on {r.letterhead}
                      </div>
                    </div>
                    {r.pdf_url && (
                      <a href={r.pdf_url} target="_blank" rel="noopener noreferrer" className={viewBtn}>
                        View PDF
                      </a>
                    )}
                    {r.pdf_url && (
                      <a href={downloadUrl(r.pdf_url, `${fileBase(r.company, r.n)}.pdf`)} className={dlBtn}>
                        ↓ PDF
                      </a>
                    )}
                    {r.docx_url && (
                      <a href={downloadUrl(r.docx_url, `${fileBase(r.company, r.n)}.docx`)} className={dlBtn}>
                        ↓ DOCX
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
