"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Activity } from "lucide-react";
import { useAuth } from "@/lib/auth-store";

export default function RegisterPage() {
  const router = useRouter();
  const { register, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
	e.preventDefault();
	setError(null);
	
	const cleanName = name.trim();
	const cleanEmail = email.trim().toLowerCase();
	if (password.length < 8) {
		setError("Password must be at least 8 characters");
		return;
		}
	try {
		await register(cleanEmail, password, cleanName);
		router.push("/");
		} 
	catch (err: any) {
		setError(err.message || "Registration failed");
		}
	}

  return (
    <div className="w-full max-w-sm card p-7">
      <div className="flex items-center gap-3 mb-6">
        <div className="size-10 rounded-xl bg-gradient-to-br from-brand to-emerald-500 flex items-center justify-center">
          <Activity className="size-6 text-white" />
        </div>
        <div>
          <div className="text-lg font-semibold">Create account</div>
          <div className="text-xs text-ink-dim">Start screening DFM, ADX, and EGX</div>
        </div>
      </div>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label">Display name</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input mt-1" />
        </div>
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
          {loading ? "Creating…" : "Create account"}
        </button>
        <div className="text-sm text-ink-muted text-center">
          Already have an account? <Link href="/login" className="text-brand hover:underline">Sign in</Link>
        </div>
      </form>
    </div>
  );
}
