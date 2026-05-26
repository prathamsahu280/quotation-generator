"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { EMPTY_ITEM, type GenError, type GenResult, type Item, type Letterhead, type ParsedData } from "@/lib/types";
import { downloadUrl, fileBase } from "@/lib/download";

const PRESET_TERMS = [
  "Prices are exclusive of GST.",
  "50% advance, balance before dispatch.",
  "Delivery: 7–10 working days from confirmed PO.",
  "Quotation valid for 15 days from date of issue.",
  "Freight extra at actuals.",
  "Warranty: 12 months from date of supply.",
  "Goods once sold will not be taken back.",
  "Subject to local jurisdiction.",
];

const input =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-800 outline-none focus:border-indigo-500";

export default function Builder({ aiMode }: { aiMode: boolean }) {
  const supabase = createClient();

  const [raw, setRaw] = useState("");
  const [buyer, setBuyer] = useState("");
  const [subject, setSubject] = useState("");
  const [ref, setRef] = useState("");
  const [date, setDate] = useState("");
  const [gst, setGst] = useState("18");
  const [signatory, setSignatory] = useState("");
  const [items, setItems] = useState<Item[]>([{ ...EMPTY_ITEM }]);
  const [terms, setTerms] = useState<string[]>([""]);

  const [letterheads, setLetterheads] = useState<Letterhead[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [count, setCount] = useState(3);
  const [makePdf, setMakePdf] = useState(true);

  const [parseStatus, setParseStatus] = useState("");
  const [genStatus, setGenStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<GenResult[]>([]);
  const [errors, setErrors] = useState<GenError[]>([]);

  const loadLetterheads = useCallback(async () => {
    const { data } = await supabase
      .from("letterheads")
      .select("*")
      .order("created_at", { ascending: true });
    if (data) setLetterheads(data as Letterhead[]);
  }, [supabase]);

  useEffect(() => {
    loadLetterheads();
  }, [loadLetterheads]);

  function fill(d: ParsedData) {
    setBuyer(d.buyer || "");
    setSubject(d.subject || "");
    setRef(d.ref || "");
    setDate(d.date || "");
    setGst(d.gst_percent || "18");
    setSignatory(d.signatory || "");
    setItems(d.items?.length ? d.items.map((it) => ({ ...EMPTY_ITEM, ...it })) : [{ ...EMPTY_ITEM }]);
    setTerms(d.terms?.length ? d.terms : [""]);
  }

  async function doParse() {
    if (!raw.trim()) {
      setParseStatus("Paste some text first.");
      return;
    }
    setParseStatus(aiMode ? "Parsing with AI…" : "Parsing…");
    try {
      const r = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: raw, ai_mode: aiMode }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Parse failed.");
      fill(d);
      const ni = d.items?.length ?? 0;
      setParseStatus(`Found ${ni} item${ni === 1 ? "" : "s"} — review below.${d._engine ? ` (${d._engine})` : ""}`);
    } catch (e: unknown) {
      setParseStatus(e instanceof Error ? e.message : "Parse failed.");
    }
  }

  function updateItem(i: number, key: keyof Item, value: string) {
    setItems((prev) => {
      const next = prev.map((it, idx) => (idx === i ? { ...it, [key]: value } : it));
      if (key === "qty" || key === "rate") {
        const it = next[i];
        const q = parseFloat(it.qty.replace(/,/g, ""));
        const rt = parseFloat(it.rate.replace(/,/g, ""));
        if (!it.amount && !isNaN(q) && !isNaN(rt)) it.amount = (q * rt).toFixed(2);
      }
      return next;
    });
  }

  async function doGenerate() {
    const cleanItems = items.filter((it) => it.description.trim());
    if (!cleanItems.length) {
      setGenStatus("Add at least one line item.");
      return;
    }
    if (!letterheads.length) {
      setGenStatus("Upload at least one letterhead first.");
      return;
    }
    setBusy(true);
    setResults([]);
    setErrors([]);
    setGenStatus(`Generating ${count}… ${aiMode ? "AI is writing each one; " : ""}this can take a few seconds.`);
    try {
      const r = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: {
            buyer,
            subject,
            ref,
            date,
            gst_percent: gst,
            signatory,
            items: cleanItems,
            terms: terms.filter((t) => t.trim()),
          },
          count,
          ai_mode: aiMode,
          make_pdf: makePdf,
          letterhead_ids: Array.from(selected),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || "Generation failed.");
      setResults(d.results || []);
      setErrors(d.errors || []);
      setGenStatus(
        `Done — ${d.results.length} generated${d.errors?.length ? `, ${d.errors.length} failed` : ""}.`,
      );
    } catch (e: unknown) {
      setGenStatus(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      setBusy(false);
    }
  }

  const card = "my-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm";
  const step = "grid h-6 w-6 place-items-center rounded-full bg-indigo-600 text-sm text-white";

  return (
    <>
      {/* STEP 2: paste */}
      <section className={card}>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <span className={step}>2</span> Paste the quote details
        </h2>
        <textarea
          rows={6}
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          onBlur={() => { if (raw.trim() && !items.some((it) => it.description.trim())) doParse(); }}
          placeholder={"Buyer: M/s ACME Pvt Ltd, Mumbai\nItems: TMT 10mm — 1000 kg @ Rs.62.50/kg; TMT 12mm — 500 kg @ 61.80\nGST 18%. Payment 50% advance, balance on delivery. Validity 15 days."}
          className={input}
        />
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={doParse}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900"
          >
            Parse →
          </button>
          <span className="text-sm text-slate-500">{parseStatus}</span>
        </div>
      </section>

      {/* STEP 3: review */}
      <section className={card}>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <span className={step}>3</span> Review &amp; edit
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm text-slate-600">
            Buyer / Ship to
            <textarea rows={3} value={buyer} onChange={(e) => setBuyer(e.target.value)} className={`mt-1 ${input}`} />
          </label>
          <div className="space-y-3">
            <label className="block text-sm text-slate-600">
              Subject
              <input value={subject} onChange={(e) => setSubject(e.target.value)} className={`mt-1 ${input}`} />
            </label>
            <label className="block text-sm text-slate-600">
              Reference / Enquiry no.
              <input value={ref} onChange={(e) => setRef(e.target.value)} className={`mt-1 ${input}`} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm text-slate-600">
                Date
                <input value={date} onChange={(e) => setDate(e.target.value)} placeholder="18-May-2026" className={`mt-1 ${input}`} />
              </label>
              <label className="block text-sm text-slate-600">
                GST %
                <input value={gst} onChange={(e) => setGst(e.target.value)} className={`mt-1 ${input}`} />
              </label>
            </div>
            <label className="block text-sm text-slate-600">
              Signatory (optional)
              <input value={signatory} onChange={(e) => setSignatory(e.target.value)} placeholder="defaults to company on letterhead" className={`mt-1 ${input}`} />
            </label>
          </div>
        </div>

        <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Line items</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400">
                <th className="px-1 pb-1">Description</th>
                <th className="px-1 pb-1 w-16">HSN</th>
                <th className="px-1 pb-1 w-16">Qty</th>
                <th className="px-1 pb-1 w-16">Unit</th>
                <th className="px-1 pb-1 w-20">Rate</th>
                <th className="px-1 pb-1 w-24">Amount</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i}>
                  {(["description", "hsn", "qty", "unit", "rate", "amount"] as (keyof Item)[]).map((k) => (
                    <td key={k} className="px-1 py-0.5">
                      <input
                        value={it[k]}
                        onChange={(e) => updateItem(i, k, e.target.value)}
                        className="w-full rounded-md border border-slate-300 px-2 py-1.5 outline-none focus:border-indigo-500"
                      />
                    </td>
                  ))}
                  <td className="text-center">
                    <button
                      onClick={() => setItems((p) => (p.length > 1 ? p.filter((_, idx) => idx !== i) : p))}
                      className="text-red-500 hover:text-red-600"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          onClick={() => setItems((p) => [...p, { ...EMPTY_ITEM }])}
          className="mt-2 rounded-lg border border-dashed border-indigo-400 px-3 py-1.5 text-sm text-indigo-600"
        >
          + Add item
        </button>

        <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Terms &amp; conditions</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {PRESET_TERMS.map((t) => (
            <button
              key={t}
              onClick={() =>
                setTerms((p) => {
                  const clean = p.filter((x) => x.trim());
                  if (clean.some((x) => x.toLowerCase() === t.toLowerCase())) return p;
                  return [...clean, t];
                })
              }
              className="rounded-full border border-slate-200 bg-indigo-50 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-600 hover:text-white"
            >
              + {t.replace(/\.$/, "")}
            </button>
          ))}
        </div>
        <div className="mt-2 space-y-2">
          {terms.map((t, i) => (
            <div key={i} className="flex gap-2">
              <input
                value={t}
                onChange={(e) => setTerms((p) => p.map((x, idx) => (idx === i ? e.target.value : x)))}
                className={input}
              />
              <button
                onClick={() => setTerms((p) => (p.length > 1 ? p.filter((_, idx) => idx !== i) : [""]))}
                className="text-red-500 hover:text-red-600"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          onClick={() => setTerms((p) => [...p, ""])}
          className="mt-2 rounded-lg border border-dashed border-indigo-400 px-3 py-1.5 text-sm text-indigo-600"
        >
          + Add term
        </button>
      </section>

      {/* STEP 4: generate */}
      <section className={card}>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <span className={step}>4</span> Generate
        </h2>

        {letterheads.length > 0 && (
          <div className="mb-4">
            <p className="mb-2 text-xs text-slate-400">
              Tick specific letterheads to use only those, or leave all unticked to pick at random.
            </p>
            <div className="flex flex-wrap gap-2">
              {letterheads.map((lh) => {
                const on = selected.has(lh.id);
                return (
                  <button
                    key={lh.id}
                    onClick={() =>
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (next.has(lh.id)) next.delete(lh.id);
                        else next.add(lh.id);
                        return next;
                      })
                    }
                    className={`rounded-full border px-3 py-1 text-xs ${
                      on ? "border-indigo-600 bg-indigo-600 text-white" : "border-slate-300 text-slate-600"
                    }`}
                  >
                    {lh.company}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-6">
          <label className="text-sm text-slate-600">
            How many variations?
            <input
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
              className={`mt-1 w-28 ${input}`}
            />
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-slate-600">
            <input type="checkbox" checked={makePdf} onChange={(e) => setMakePdf(e.target.checked)} />
            Also make PDF
          </label>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={doGenerate}
            disabled={busy}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            Generate quotations
          </button>
          <span className="text-sm text-slate-500">{genStatus}</span>
        </div>

        <div className="mt-4 space-y-3">
          {results.map((r) => (
            <div key={r.n} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="font-semibold">#{r.n} · {r.company}</div>
              <div className="mt-0.5 text-sm text-slate-500">{r.summary} | on {r.letterhead}</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {r.pdf_url && (
                  <a
                    href={r.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded-md border border-indigo-500 px-3 py-1 text-sm text-indigo-600 hover:bg-indigo-600 hover:text-white"
                  >
                    View PDF
                  </a>
                )}
                {r.pdf_url && (
                  <a
                    href={downloadUrl(r.pdf_url, `${fileBase(r.company, r.n)}.pdf`)}
                    className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-indigo-500 hover:text-indigo-600"
                  >
                    ↓ PDF
                  </a>
                )}
                {r.docx_url && (
                  <a
                    href={downloadUrl(r.docx_url, `${fileBase(r.company, r.n)}.docx`)}
                    className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:border-indigo-500 hover:text-indigo-600"
                  >
                    ↓ DOCX
                  </a>
                )}
              </div>
            </div>
          ))}
          {errors.map((e) => (
            <div key={`e-${e.n}`} className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm">
              <div className="font-semibold text-red-700">#{e.n} · {e.company} — failed</div>
              <div className="text-red-600">{e.error}</div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
