import { createClient } from "@supabase/supabase-js";

// Service-role client — SERVER ONLY. Bypasses RLS; never import in client code.
// Used to write generated outputs to storage and mint signed download URLs.
export function createAdminClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );
}
