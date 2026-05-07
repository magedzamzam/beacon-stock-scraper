"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Activity } from "lucide-react";
import { useAuth } from "@/lib/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const { login, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Login failed");
    }
  }

  return (
    <div className="w-full max-w-sm card p-7">
      <div className="flex items-center gap-3 mb-6">
        <div className="size-10 rounded-xl bg-gradient-to-br from-brand to-emerald-500 flex items-center justify-center">
          <Activity className="size-6 text-white" />
        </div>
        <div>
          <div className="text-lg font-semibold">Beacon Screener</div>
          <div className="text-xs text-ink-dim">Sign in to your account</div>
        </div>
      </div>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label">Email</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="input mt-1" />
        </div>
        <div>
          <label className="label">Password</label>
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="input mt-1" />
        </div>
        {error && <div className="text-sm text-verdict-avoid">{error}</div>}
        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
        <div className="text-sm text-ink-muted text-center">
          No account? <Link href="/register" className="text-brand hover:underline">Register</Link>
        </div>
      </form>
    </div>
  );
}
