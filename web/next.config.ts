import type { NextConfig } from "next";
import path from "node:path";

// Hosts allowed to load Next dev resources cross-origin (dev server only;
// irrelevant for `next build` + `next start`). Comma-separate extra hosts in
// ALLOWED_DEV_ORIGINS, e.g. "45.11.229.172,quotes.example.com".
const devOrigins = (process.env.ALLOWED_DEV_ORIGINS || "45.11.229.172")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  // Pin the workspace root so Next doesn't pick up an unrelated parent lockfile.
  turbopack: { root: path.join(__dirname) },
  ...(devOrigins.length ? { allowedDevOrigins: devOrigins } : {}),
};

export default nextConfig;