"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import Letterheads from "@/components/Letterheads";
import Builder from "@/components/Builder";

export default function QuotationApp({ email }: { email: string }) {
  const router = useRouter();
  const supabase = createClient();
  const [aiMode, setAiMode] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [pdfEngine, setPdfEngine] = useState<string>("");

  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((s) => {
        setAiAvailable(!!s.ai_available);
        setPdfEngine(s.pdf_engine ?? "");
      })
      .catch(() => {});
  }, []);

  async function logout() {
    await supabase.auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      {/* top bar */}
      <div className="sticky top-0 z-20 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-6 py-3">
          <span className="font-bold text-indigo-700">Quotation Generator</span>
          <Link href="/history" className="text-sm text-slate-500 hover:text-indigo-600">
            History
          </Link>
          <span className="flex-1" />
          <label
            title={
              aiAvailable
                ? "Use Gemini to parse input and write each quotation"
                : "AI mode unavailable — no Gemini key on the server"
            }
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold ${
              aiAvailable ? "border-slate-200 bg-indigo-50" : "border-slate-200 bg-slate-100 opacity-50"
            }`}
          >
            <input
              type="checkbox"
              disabled={!aiAvailable}
              checked={aiMode}
              onChange={(e) => setAiMode(e.target.checked)}
            />
            AI mode
          </label>
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
        <header className="mb-2">
          <h1 className="text-2xl font-bold">Quotation Generator</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload your blank letterheads, paste the quote details, and generate multiple
            distinctly-styled quotations — each on a different letterhead.
          </p>
          {pdfEngine === "none" && (
            <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              No PDF engine on the doc-gen server — output will be DOCX only. Install LibreOffice
              or MS Word for PDF.
            </p>
          )}
        </header>

        <Letterheads />
        <Builder aiMode={aiMode && aiAvailable} />
      </main>
    </div>
  );
}
