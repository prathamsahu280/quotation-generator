// Helpers for turning a Supabase signed URL into a forced-download URL.
// Appending `&download=<name>` makes Storage send Content-Disposition: attachment
// (verified against the project); the plain URL views inline in the browser.

export function fileBase(company: string, n: number): string {
  const c = (company || "quotation")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 24) || "quotation";
  return `${c}_${n}`;
}

export function downloadUrl(signedUrl: string, filename: string): string {
  const sep = signedUrl.includes("?") ? "&" : "?";
  return `${signedUrl}${sep}download=${encodeURIComponent(filename)}`;
}
