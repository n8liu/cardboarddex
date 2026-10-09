"use client";

import { useState } from "react";
import { AdminApiError, adminRequest } from "@/lib/admin-api";

export function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <form className="mx-auto mt-12 max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm" onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await adminRequest("/login", { method: "POST", body: JSON.stringify({ secret }) });
      setSecret(""); onLogin();
    } catch (error) {
      setError(error instanceof AdminApiError && error.status === 401 ? "Invalid admin secret." : error instanceof Error ? error.message : "Unable to log in.");
    } finally { setBusy(false); }
  }}>
    <h2 className="text-xl font-semibold">Admin login</h2>
    <p className="mt-2 text-sm text-slate-500">Enter your admin secret to view private traffic statistics.</p>
    <label htmlFor="admin-secret" className="mt-6 block text-sm font-medium">Admin secret</label>
    <input id="admin-secret" type="password" autoComplete="current-password" required maxLength={512} value={secret} onChange={(event) => setSecret(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 p-3" />
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    <button disabled={busy} className="mt-5 w-full rounded-lg bg-emerald-800 px-4 py-3 font-semibold text-white disabled:opacity-50">{busy ? "Signing in…" : "Sign in"}</button>
  </form>;
}
