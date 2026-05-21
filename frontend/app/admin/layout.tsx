"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-store";
import { LayoutDashboard, Database, FileUp, FileSpreadsheet, History, SlidersHorizontal, Bell, Bot } from "lucide-react";

const TABS = [
  { href: "/admin",             label: "Overview",    icon: LayoutDashboard, exact: true },
  { href: "/admin/stocks",      label: "Stocks",      icon: Database },
  { href: "/admin/imports",     label: "CSV import",  icon: FileUp },
  { href: "/admin/bulk-import", label: "Bulk import", icon: FileSpreadsheet },
  { href: "/admin/alerts",      label: "Alerts",      icon: Bell },
  { href: "/admin/bot",         label: "Bot config",  icon: Bot },
  { href: "/admin/history",     label: "History",     icon: History },
  { href: "/admin/settings",    label: "Settings",    icon: SlidersHorizontal },
];


export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();

  if (!user?.is_admin) {
    return <div className="card p-8 text-center text-ink-muted">Admin only.</div>;
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <p className="text-ink-muted text-sm mt-1">Pipeline triggers, stock catalog, imports.</p>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map(({ href, label, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={
                "flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 -mb-px transition-colors " +
                (active
                  ? "border-brand text-ink"
                  : "border-transparent text-ink-muted hover:text-ink")
              }
            >
              <Icon className="size-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
