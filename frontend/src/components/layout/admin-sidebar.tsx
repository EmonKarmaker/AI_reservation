"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Calendar, LayoutDashboard, ListChecks, MessageCircleQuestion, Settings, LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/store/auth-store";

const NAV = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/services", label: "Services", icon: ListChecks },
  { href: "/admin/hours", label: "Hours", icon: Calendar },
  { href: "/admin/faqs", label: "FAQs", icon: MessageCircleQuestion },
  { href: "/admin/settings", label: "Settings", icon: Settings },
];

export function AdminSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-card">
      <div className="border-b p-4">
        <p className="font-semibold">AI Reservation</p>
        <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t p-2">
        <Button variant="ghost" className="w-full justify-start gap-3" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  );
}
