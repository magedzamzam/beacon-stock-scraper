"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  LayoutDashboard, Search, Briefcase, Star, Shield, LogOut, LogIn, User as UserIcon, Activity,
} from "lucide-react";
import { useAuth } from "@/lib/auth-store";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener", label: "Screener", icon: Search },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/watchlists", label: "Watchlists", icon: Star },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, init, initialized, logout } = useAuth();

  useEffect(() => { init(); }, [init]);

  // Routes that don't need auth UI
  const isAuthRoute = pathname?.startsWith("/login") || pathname?.startsWith("/register");

  useEffect(() => {
    if (!initialized) return;
    if (!user && !isAuthRoute) router.replace("/login");
  }, [user, initialized, isAuthRoute, router]);

  if (!initialized) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-ink-muted">Loading…</div>
      </div>
    );
  }

  if (isAuthRoute) {
    return <main className="min-h-screen flex items-center justify-center p-4">{children}</main>;
  }

  if (!user) return null; // redirecting

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="hidden md:flex md:w-64 lg:w-72 flex-col border-r border-border bg-bg-card">
        <div className="px-5 py-6 flex items-center gap-3 border-b border-border">
          <div className="size-9 rounded-lg bg-gradient-to-br from-brand to-emerald-500 flex items-center justify-center">
            <Activity className="size-5 text-white" />
          </div>
          <div>
            <div className="font-semibold tracking-tight">Beacon</div>
            <div className="text-[10px] uppercase tracking-widest text-ink-dim">DFM · ADX · EGX</div>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((n) => {
            const Active = pathname === n.href || (n.href !== "/" && pathname?.startsWith(n.href));
            const Icon = n.icon;
            return (
              <Link key={n.href} href={n.href} className={cn("nav-link", Active && "nav-link-active")}>
                <Icon className="size-4" /> {n.label}
              </Link>
            );
          })}
          {user.is_admin && (
            <Link href="/admin" className={cn("nav-link", pathname?.startsWith("/admin") && "nav-link-active")}>
              <Shield className="size-4" /> Admin
            </Link>
          )}
        </nav>
        <div className="p-3 border-t border-border">
          <div className="flex items-center gap-2 px-2 py-2 text-sm">
            <div className="size-8 rounded-full bg-bg-elevated flex items-center justify-center">
              <UserIcon className="size-4 text-ink-muted" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="truncate text-ink">{user.display_name || user.email.split("@")[0]}</div>
              <div className="truncate text-xs text-ink-dim">{user.email}</div>
            </div>
            <button onClick={logout} title="Logout" className="text-ink-muted hover:text-ink p-1.5">
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-40 h-14 border-b border-border bg-bg-card flex items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2">
          <div className="size-7 rounded-md bg-gradient-to-br from-brand to-emerald-500 flex items-center justify-center">
            <Activity className="size-4 text-white" />
          </div>
          <span className="font-semibold">Beacon</span>
        </Link>
        <button onClick={logout} className="text-ink-muted"><LogOut className="size-5" /></button>
      </div>

      {/* Mobile bottom nav */}
      <div className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-border bg-bg-card">
        <div className="grid grid-cols-4">
          {NAV.map((n) => {
            const Active = pathname === n.href || (n.href !== "/" && pathname?.startsWith(n.href));
            const Icon = n.icon;
            return (
              <Link key={n.href} href={n.href}
                    className={cn("flex flex-col items-center gap-1 py-2.5 text-[11px]",
                                  Active ? "text-ink" : "text-ink-muted")}>
                <Icon className="size-5" />
                {n.label}
              </Link>
            );
          })}
        </div>
      </div>

      <main className="flex-1 min-w-0 md:py-0 pt-14 pb-20 md:pb-0">
        <div className="p-4 md:p-8 max-w-[1400px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
