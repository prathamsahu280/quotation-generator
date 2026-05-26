"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Letterhead } from "@/lib/types";

export default function Letterheads() {
  const supabase = createClient();
  const [items, setItems] = useState<Letterhead[]>([]);
  const [status, setStatus] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const { data, error } = await supabase
      .from("letterheads")
      .select("*")
      .order("created_at", { ascending: true });
    if (!error && data) setItems(data as Letterhead[]);
  }, [supabase]);

  useEffect(() => {
    load();
  }, [load]);

  async function upload(files: FileList | File[]) {
    const list = Array.from(files).filter((f) => /\.(docx|pdf)$/i.test(f.name));
    if (!list.length) {
      setStatus("Only .docx or .pdf letterheads are supported.");
      return;
    }
    for (const file of list) {
      const isPdf = /\.pdf$/i.test(file.name);
      setStatus(isPdf ? `Converting ${file.name}…` : `Uploading ${file.name}…`);
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/letterheads", { method: "POST", body: fd });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setStatus(`Upload failed: ${d.error || r.statusText}`);
        continue;
      }
    }
    setStatus("");
    load();
  }

  async function remove(lh: Letterhead) {
    if (!confirm(`Remove "${lh.company}"?`)) return;
    await supabase.storage.from("letterheads").remove([lh.storage_path]);
    await supabase.from("letterheads").delete().eq("id", lh.id);
    load();
  }

  async function rename(lh: Letterhead, company: string) {
    const v = company.trim();
    if (!v || v === lh.company) return;
    await supabase.from("letterheads").update({ company: v }).eq("id", lh.id);
    setItems((prev) => prev.map((x) => (x.id === lh.id ? { ...x, company: v } : x)));
  }

  return (
    <section className="my-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-indigo-600 text-sm text-white">
          1
        </span>
        Letterheads
      </h2>

      <div
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) upload(e.dataTransfer.files);
        }}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-6 text-center text-sm transition ${
          dragging ? "border-indigo-500 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-500"
        }`}
      >
        Drop blank <strong>.docx</strong> or <strong>.pdf</strong> letterheads here, or click to browse.
        <input
          ref={fileRef}
          type="file"
          accept=".docx,.pdf"
          multiple
          hidden
          onChange={(e) => e.target.files && upload(e.target.files)}
        />
      </div>
      {status && <p className="mt-2 text-sm text-slate-500">{status}</p>}
      <p className="mt-2 text-xs text-slate-400">
        These are <strong>your</strong> letterheads — private to your account. The company name is
        editable; click it to fix.
      </p>

      <ul className="mt-3 space-y-2">
        {items.length === 0 && (
          <li className="text-sm text-slate-400">No letterheads yet — upload some above.</li>
        )}
        {items.map((lh) => (
          <li
            key={lh.id}
            className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
          >
            <input
              defaultValue={lh.company}
              onBlur={(e) => rename(lh, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
              title="Company name (click to edit)"
              className="w-56 rounded-md border border-transparent bg-transparent px-2 py-1 font-semibold hover:border-slate-300 focus:border-indigo-500 focus:bg-white focus:outline-none"
            />
            <span className="truncate text-xs text-slate-400" title={lh.original_name}>
              {lh.original_name}
            </span>
            <span className="flex-1" />
            <button
              onClick={() => remove(lh)}
              className="text-red-500 hover:text-red-600"
              title="Remove"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
