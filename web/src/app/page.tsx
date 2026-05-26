import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import QuotationApp from "@/components/QuotationApp";

export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return <QuotationApp email={user.email ?? ""} />;
}
