"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/client";
import {
  ApiError,
  type BusinessOut,
  type BusinessSettingsOut,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Profile form state (mirrors BusinessUpdate on the backend)
// ---------------------------------------------------------------------------

interface ProfileFormState {
  name: string;
  description: string;
  industry: string;
  phone: string;
  email: string;
  website: string;
  address: string;
  ai_personality: string;
  ai_greeting: string;
  booking_window_days: string;
  cancellation_hours: string;
}

function profileFromBusiness(b: BusinessOut): ProfileFormState {
  return {
    name: b.name,
    description: b.description ?? "",
    industry: b.industry ?? "",
    phone: b.phone ?? "",
    email: b.email ?? "",
    website: b.website ?? "",
    address: b.address ?? "",
    ai_personality: b.ai_personality ?? "",
    ai_greeting: b.ai_greeting ?? "",
    booking_window_days: String(b.booking_window_days),
    cancellation_hours: String(b.cancellation_hours),
  };
}

function profilePayload(form: ProfileFormState) {
  return {
    name: form.name,
    description: form.description || null,
    industry: form.industry || null,
    phone: form.phone || null,
    email: form.email || null,
    website: form.website || null,
    address: form.address || null,
    ai_personality: form.ai_personality || null,
    ai_greeting: form.ai_greeting || null,
    booking_window_days: Number(form.booking_window_days),
    cancellation_hours: Number(form.cancellation_hours),
  };
}

// ---------------------------------------------------------------------------
// Settings form state (mirrors BusinessSettingsUpdate on the backend)
// ---------------------------------------------------------------------------

interface SettingsFormState {
  require_payment_at_booking: boolean;
  deposit_percentage: string;
  auto_confirm_bookings: boolean;
  send_reminder_hours_before: string;
  escalation_email: string;
  max_daily_bookings: string;
}

function settingsFromOut(s: BusinessSettingsOut): SettingsFormState {
  return {
    require_payment_at_booking: s.require_payment_at_booking,
    deposit_percentage: String(s.deposit_percentage),
    auto_confirm_bookings: s.auto_confirm_bookings,
    send_reminder_hours_before: String(s.send_reminder_hours_before),
    escalation_email: s.escalation_email ?? "",
    max_daily_bookings: s.max_daily_bookings === null ? "" : String(s.max_daily_bookings),
  };
}

function settingsPayload(form: SettingsFormState) {
  return {
    require_payment_at_booking: form.require_payment_at_booking,
    deposit_percentage: Number(form.deposit_percentage),
    auto_confirm_bookings: form.auto_confirm_bookings,
    send_reminder_hours_before: Number(form.send_reminder_hours_before),
    escalation_email: form.escalation_email || null,
    max_daily_bookings:
      form.max_daily_bookings.trim() === "" ? null : Number(form.max_daily_bookings),
  };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const EMPTY_PROFILE: ProfileFormState = {
  name: "",
  description: "",
  industry: "",
  phone: "",
  email: "",
  website: "",
  address: "",
  ai_personality: "",
  ai_greeting: "",
  booking_window_days: "30",
  cancellation_hours: "24",
};

const EMPTY_SETTINGS: SettingsFormState = {
  require_payment_at_booking: false,
  deposit_percentage: "0",
  auto_confirm_bookings: true,
  send_reminder_hours_before: "24",
  escalation_email: "",
  max_daily_bookings: "",
};

export default function SettingsPage() {
  const [profile, setProfile] = useState<ProfileFormState>(EMPTY_PROFILE);
  const [settings, setSettings] = useState<SettingsFormState>(EMPTY_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  async function loadAll() {
    setLoading(true);
    try {
      const [b, s] = await Promise.all([
        api.get<BusinessOut>("/admin/business"),
        api.get<BusinessSettingsOut>("/admin/business/settings"),
      ]);
      setProfile(profileFromBusiness(b));
      setSettings(settingsFromOut(s));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleSaveProfile() {
    if (!profile.name.trim()) {
      toast.error("Business name is required");
      return;
    }
    setSavingProfile(true);
    try {
      const updated = await api.patch<BusinessOut>("/admin/business", profilePayload(profile));
      setProfile(profileFromBusiness(updated));
      toast.success("Business profile updated");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleSaveSettings() {
    setSavingSettings(true);
    try {
      const updated = await api.patch<BusinessSettingsOut>(
        "/admin/business/settings",
        settingsPayload(settings),
      );
      setSettings(settingsFromOut(updated));
      toast.success("Booking settings updated");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setSavingSettings(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-muted-foreground">Business profile, AI personality, and booking rules</p>
      </div>

      {/* ----- Business profile ----- */}
      <Card>
        <CardHeader>
          <CardTitle>Business profile</CardTitle>
          <CardDescription>What customers and the AI see about you</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={profile.name}
                onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="industry">Industry</Label>
              <Input
                id="industry"
                value={profile.industry}
                onChange={(e) => setProfile({ ...profile, industry: e.target.value })}
                placeholder="e.g. dental, hvac, law"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <textarea
              id="description"
              value={profile.description}
              onChange={(e) => setProfile({ ...profile, description: e.target.value })}
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="phone">Phone</Label>
              <Input
                id="phone"
                value={profile.phone}
                onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={profile.email}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="website">Website</Label>
              <Input
                id="website"
                value={profile.website}
                onChange={(e) => setProfile({ ...profile, website: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="address">Address</Label>
              <Input
                id="address"
                value={profile.address}
                onChange={(e) => setProfile({ ...profile, address: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="ai_personality">AI personality</Label>
            <textarea
              id="ai_personality"
              value={profile.ai_personality}
              onChange={(e) => setProfile({ ...profile, ai_personality: e.target.value })}
              rows={3}
              placeholder="How should the AI speak? e.g. 'Warm, professional, and concise.'"
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ai_greeting">AI greeting</Label>
            <textarea
              id="ai_greeting"
              value={profile.ai_greeting}
              onChange={(e) => setProfile({ ...profile, ai_greeting: e.target.value })}
              rows={2}
              placeholder="First message the AI sends. e.g. 'Hi! Thanks for contacting Dhaka Dental. How can I help?'"
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="booking_window_days">Booking window (days)</Label>
              <Input
                id="booking_window_days"
                type="number"
                min={1}
                max={365}
                value={profile.booking_window_days}
                onChange={(e) =>
                  setProfile({ ...profile, booking_window_days: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cancellation_hours">Cancellation notice (hours)</Label>
              <Input
                id="cancellation_hours"
                type="number"
                min={0}
                max={720}
                value={profile.cancellation_hours}
                onChange={(e) =>
                  setProfile({ ...profile, cancellation_hours: e.target.value })
                }
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button onClick={handleSaveProfile} disabled={savingProfile}>
              {savingProfile ? "Saving…" : "Save profile"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ----- Booking settings ----- */}
      <Card>
        <CardHeader>
          <CardTitle>Booking settings</CardTitle>
          <CardDescription>How the AI handles new bookings and follow-ups</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.require_payment_at_booking}
              onChange={(e) =>
                setSettings({ ...settings, require_payment_at_booking: e.target.checked })
              }
              className="h-4 w-4"
            />
            Require payment at booking
          </label>

          <div className="space-y-2">
            <Label htmlFor="deposit_percentage">Deposit percentage (0-100)</Label>
            <Input
              id="deposit_percentage"
              type="number"
              min={0}
              max={100}
              value={settings.deposit_percentage}
              onChange={(e) =>
                setSettings({ ...settings, deposit_percentage: e.target.value })
              }
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.auto_confirm_bookings}
              onChange={(e) =>
                setSettings({ ...settings, auto_confirm_bookings: e.target.checked })
              }
              className="h-4 w-4"
            />
            Auto-confirm bookings (otherwise admin reviews each one)
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="reminder">Reminder hours before</Label>
              <Input
                id="reminder"
                type="number"
                min={0}
                max={168}
                value={settings.send_reminder_hours_before}
                onChange={(e) =>
                  setSettings({ ...settings, send_reminder_hours_before: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_daily">Max daily bookings (blank = unlimited)</Label>
              <Input
                id="max_daily"
                type="number"
                min={1}
                value={settings.max_daily_bookings}
                onChange={(e) =>
                  setSettings({ ...settings, max_daily_bookings: e.target.value })
                }
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="escalation_email">Escalation email</Label>
            <Input
              id="escalation_email"
              type="email"
              value={settings.escalation_email}
              onChange={(e) =>
                setSettings({ ...settings, escalation_email: e.target.value })
              }
              placeholder="Where the AI sends edge-case bookings for human review"
            />
          </div>

          <div className="flex justify-end">
            <Button onClick={handleSaveSettings} disabled={savingSettings}>
              {savingSettings ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
