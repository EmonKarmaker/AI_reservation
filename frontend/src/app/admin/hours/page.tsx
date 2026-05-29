"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/client";
import {
  ApiError,
  type DayOfWeek,
  type OperatingHoursDay,
  type OperatingHoursOut,
} from "@/lib/api/types";

const DAY_ORDER: DayOfWeek[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_LABELS: Record<DayOfWeek, string> = {
  mon: "Monday",
  tue: "Tuesday",
  wed: "Wednesday",
  thu: "Thursday",
  fri: "Friday",
  sat: "Saturday",
  sun: "Sunday",
};

const DEFAULT_OPEN = "09:00:00";
const DEFAULT_CLOSE = "17:00:00";

function fullWeek(loaded: OperatingHoursDay[]): OperatingHoursDay[] {
  const byDay = new Map(loaded.map((d) => [d.day_of_week, d]));
  return DAY_ORDER.map((day) =>
    byDay.get(day) ?? {
      day_of_week: day,
      open_time: DEFAULT_OPEN,
      close_time: DEFAULT_CLOSE,
      is_closed: false,
    },
  );
}

// HTML time inputs use HH:MM. The API returns/accepts HH:MM:SS.
function toInputValue(t: string | null | undefined): string {
  if (!t) return "";
  return t.slice(0, 5);
}
function fromInputValue(v: string): string {
  if (!v) return DEFAULT_OPEN;
  return v.length === 5 ? `${v}:00` : v;
}

export default function HoursPage() {
  const [days, setDays] = useState<OperatingHoursDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  async function loadHours() {
    setLoading(true);
    try {
      const data = await api.get<OperatingHoursOut>("/admin/hours");
      setDays(fullWeek(data.days));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to load hours");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHours();
  }, []);

  function updateDay(day: DayOfWeek, patch: Partial<OperatingHoursDay>) {
    setDays((prev) =>
      prev.map((d) => (d.day_of_week === day ? { ...d, ...patch } : d)),
    );
  }

  async function handleSave() {
    setSaving(true);
    try {
      const payload = {
        days: days.map((d) => ({
          day_of_week: d.day_of_week,
          open_time: d.is_closed ? null : fromInputValue(toInputValue(d.open_time)),
          close_time: d.is_closed ? null : fromInputValue(toInputValue(d.close_time)),
          is_closed: d.is_closed,
        })),
      };
      const data = await api.put<OperatingHoursOut>("/admin/hours", payload);
      setDays(fullWeek(data.days));
      toast.success("Hours saved");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Operating hours</h1>
          <p className="text-muted-foreground">When the AI will accept bookings</p>
        </div>
        <Button onClick={handleSave} disabled={saving || loading}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>

      <div className="rounded-md border bg-card p-4">
        {loading ? (
          <p className="text-center text-muted-foreground">Loading…</p>
        ) : (
          <div className="space-y-3">
            {days.map((d) => (
              <div
                key={d.day_of_week}
                className="grid grid-cols-[140px_120px_1fr_1fr] items-center gap-3"
              >
                <Label className="font-medium">{DAY_LABELS[d.day_of_week]}</Label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={d.is_closed}
                    onChange={(e) =>
                      updateDay(d.day_of_week, { is_closed: e.target.checked })
                    }
                    className="h-4 w-4"
                  />
                  Closed
                </label>
                <Input
                  type="time"
                  value={toInputValue(d.open_time)}
                  disabled={d.is_closed}
                  onChange={(e) =>
                    updateDay(d.day_of_week, {
                      open_time: fromInputValue(e.target.value),
                    })
                  }
                />
                <Input
                  type="time"
                  value={toInputValue(d.close_time)}
                  disabled={d.is_closed}
                  onChange={(e) =>
                    updateDay(d.day_of_week, {
                      close_time: fromInputValue(e.target.value),
                    })
                  }
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
