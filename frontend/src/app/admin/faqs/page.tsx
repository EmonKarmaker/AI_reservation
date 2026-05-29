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
import { ApiError, type FaqOut } from "@/lib/api/types";

interface FormState {
  question: string;
  answer: string;
  category: string;
  is_active: boolean;
  display_order: string;
}

const EMPTY_FORM: FormState = {
  question: "",
  answer: "",
  category: "",
  is_active: true,
  display_order: "0",
};

function formFromFaq(f: FaqOut): FormState {
  return {
    question: f.question,
    answer: f.answer,
    category: f.category ?? "",
    is_active: f.is_active,
    display_order: String(f.display_order),
  };
}

function buildPayload(form: FormState) {
  return {
    question: form.question,
    answer: form.answer,
    category: form.category || null,
    is_active: form.is_active,
    display_order: Number(form.display_order),
  };
}

export default function FaqsPage() {
  const [faqs, setFaqs] = useState<FaqOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<FaqOut | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  async function loadFaqs() {
    setLoading(true);
    try {
      const data = await api.get<FaqOut[]>("/admin/faqs");
      setFaqs(data);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to load FAQs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadFaqs();
  }, []);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(faq: FaqOut) {
    setEditing(faq);
    setForm(formFromFaq(faq));
    setDialogOpen(true);
  }

  async function handleSave() {
    if (!form.question.trim() || !form.answer.trim()) {
      toast.error("Question and answer are required");
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload(form);
      if (editing) {
        await api.patch<FaqOut>(`/admin/faqs/${editing.id}`, payload);
        toast.success("FAQ updated");
      } else {
        await api.post<FaqOut>("/admin/faqs", payload);
        toast.success("FAQ created");
      }
      setDialogOpen(false);
      loadFaqs();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(faq: FaqOut) {
    if (!confirm(`Delete this FAQ?\n\n"${faq.question}"`)) {
      return;
    }
    try {
      await api.del(`/admin/faqs/${faq.id}`);
      toast.success("FAQ deleted");
      loadFaqs();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">FAQs</h1>
          <p className="text-muted-foreground">Questions the AI can answer automatically</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          New FAQ
        </Button>
      </div>

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Question</TableHead>
              <TableHead className="w-[140px]">Category</TableHead>
              <TableHead className="w-[100px]">Active</TableHead>
              <TableHead className="w-[140px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            ) : faqs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No FAQs yet. Click &ldquo;New FAQ&rdquo; to add one.
                </TableCell>
              </TableRow>
            ) : (
              faqs.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="font-medium max-w-md truncate">{f.question}</TableCell>
                  <TableCell>{f.category ?? "—"}</TableCell>
                  <TableCell>{f.is_active ? "Yes" : "No"}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(f)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(f)}
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
            <DialogTitle>{editing ? "Edit FAQ" : "New FAQ"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "Update what the AI tells customers."
                : "Add a question + answer the AI can use."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="question">Question</Label>
              <Input
                id="question"
                value={form.question}
                onChange={(e) => setForm({ ...form, question: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="answer">Answer</Label>
              <textarea
                id="answer"
                value={form.answer}
                onChange={(e) => setForm({ ...form, answer: e.target.value })}
                rows={4}
                className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="category">Category</Label>
                <Input
                  id="category"
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  placeholder="e.g. pricing, hours"
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
              Active (AI will use this FAQ)
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
