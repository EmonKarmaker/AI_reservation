"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { AdminSidebar } from "@/components/layout/admin-sidebar";
import { useAuthStore } from "@/lib/store/auth-store";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, initialized, checkAuth } = useAuthStore();

  useEffect(() => {
    if (!initialized) {
      checkAuth();
    }
  }, [initialized, checkAuth]);

  useEffect(() => {
    if (initialized && !user) {
      router.replace("/login");
    }
  }, [initialized, user, router]);

  if (!initialized) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!user) {
    // Redirect effect will fire; render nothing meanwhile.
    return null;
  }

  return (
    <div className="flex">
      <AdminSidebar />
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
