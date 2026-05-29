"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api/client";
import { ApiError, type ServiceOut } from "@/lib/api/types";

interface FormState {
  name: string;
  description: string;
  duration_minutes: string;
  buffer_minutes: string;
  price: string;
  is_active: boolean;
  display_order: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  description: "",
  duration_minutes: "30",
  buffer_minutes: "0",
  price: "0",
  is_active: true,
  display_order: "0",
};

function formFromService(s: ServiceOut): FormState {
  return {
    name: s.name,
    description: s.description ?? "",
    duration_minutes: String(s.duration_minutes),
    buffer_minutes: String(s.buffer_minutes),
    price: s.price,
    is_active: s.is_active,
    display_order: String(s.display_order),
  };
}

function buildPayload(form: FormState) {
  return {
    name: form.name,
    description: form.description || null,
    duration_minutes: Number(form.duration_minutes),
    buffer_minutes: Number(form.buffer_minutes),
    price: form.price,
    is_active: form.is_active,
    display_order: Number(form.display_order),
  };
}

export default function ServicesPage() {
  const [services, setServices] = useState<ServiceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceOut | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  async function loadServices() {
    setLoading(true);
    try {
      const data = await api.get<ServiceOut[]>("/admin/services");
      setServices(data);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to load services");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadServices();
  }, []);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(service: ServiceOut) {
    setEditing(service);
    setForm(formFromService(service));
    setDialogOpen(true);
  }

  async function handleSave() {
    if (!form.name.trim()) {
      toast.error("Name is required");
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(form);
      if (editing) {
        await api.patch<ServiceOut>(`/admin/services/${editing.id}`, payload);
        toast.success("Service updated");
      } else {
        await api.post<ServiceOut>("/admin/services", payload);
        toast.success("Service created");
      }
      setDialogOpen(false);
      loadServices();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(service: ServiceOut) {
    if (!confirm(`Delete "${service.name}"? This can't be undone from the UI.`)) {
      return;
    }
    try {
      await api.del(`/admin/services/${service.id}`);
      toast.success("Service deleted");
      loadServices();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Services</h1>
          <p className="text-muted-foreground">What customers can book</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          New service
        </Button>
      </div>

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="w-[100px]">Duration</TableHead>
              <TableHead className="w-[100px]">Price</TableHead>
              <TableHead className="w-[100px]">Active</TableHead>
              <TableHead className="w-[140px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            ) : services.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No services yet. Click &ldquo;New service&rdquo; to add one.
                </TableCell>
              </TableRow>
            ) : (
              services.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell>{s.duration_minutes} min</TableCell>
                  <TableCell>{s.price}</TableCell>
                  <TableCell>{s.is_active ? "Yes" : "No"}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(s)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(s)}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit service" : "New service"}</DialogTitle>
            <DialogDescription>
              {editing ? "Update what customers see and pay." : "Add a new bookable service."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="duration">Duration (min)</Label>
                <Input
                  id="duration"
                  type="number"
                  min={1}
                  value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="buffer">Buffer (min)</Label>
                <Input
                  id="buffer"
                  type="number"
                  min={0}
                  value={form.buffer_minutes}
                  onChange={(e) => setForm({ ...form, buffer_minutes: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="price">Price</Label>
                <Input
                  id="price"
                  inputMode="decimal"
                  value={form.price}
                  onChange={(e) => setForm({ ...form, price: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="display_order">Display order</Label>
                <Input
                  id="display_order"
                  type="number"
                  min={0}
                  value={form.display_order}
                  onChange={(e) => setForm({ ...form, display_order: e.target.value })}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                className="h-4 w-4"
              />
              Active (customers can book this service)
            </label>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
