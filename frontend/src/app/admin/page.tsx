"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import type { BusinessOut } from "@/lib/api/types";

export default function AdminDashboardPage() {
  const [business, setBusiness] = useState<BusinessOut | null>(null);

  useEffect(() => {
    api.get<BusinessOut>("/admin/business").then(setBusiness).catch(() => setBusiness(null));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-muted-foreground">
          {business ? business.name : "Loading your business…"}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Bookings</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">—</p>
            <p className="text-xs text-muted-foreground">Coming in a later phase</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Revenue</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">—</p>
            <p className="text-xs text-muted-foreground">Coming in a later phase</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Status</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold capitalize">{business?.status ?? "—"}</p>
            <p className="text-xs text-muted-foreground">Business status</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
