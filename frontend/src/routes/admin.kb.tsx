import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { adminApi } from "../lib/admin-api";
import { getAgent } from "../lib/auth";

export const Route = createFileRoute("/admin/kb")({
  component: KBPage,
});

function KBPage() {
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const isAdmin = getAgent()?.role === "admin";

  const listQuery = useQuery({
    queryKey: ["admin", "kb", "list"],
    queryFn: () => adminApi.kbList(),
  });

  return (
    <div className="flex h-full">
      <aside className="w-80 flex-shrink-0 overflow-y-auto border-r border-neutral-200 bg-white">
        <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
          <h1 className="text-sm font-semibold">Knowledge Base</h1>
          {isAdmin && (
            <button
              onClick={() => setSelectedId("new")}
              className="rounded-md bg-neutral-900 px-2 py-1 text-xs font-medium text-white"
            >
              + New
            </button>
          )}
        </div>
        <ul>
          {listQuery.data?.map((doc) => (
            <li key={doc.id}>
              <button
                onClick={() => setSelectedId(doc.id)}
                className={`block w-full border-b border-neutral-100 px-4 py-3 text-left text-sm hover:bg-neutral-50 ${
                  selectedId === doc.id ? "bg-neutral-100" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{doc.title}</span>
                  {!doc.is_active && (
                    <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-[10px] text-neutral-500">
                      inactive
                    </span>
                  )}
                </div>
                <div className="mt-1 text-xs text-neutral-500">
                  {doc.category ?? "uncategorized"} · v{doc.version}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {selectedId === "new" ? (
          <DocumentEditor mode="new" isAdmin={isAdmin} onDone={(id) => setSelectedId(id)} />
        ) : selectedId ? (
          <DocumentEditor mode="edit" docId={selectedId} isAdmin={isAdmin} onDone={() => {}} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-neutral-400">
            Select a document, or create a new one.
          </div>
        )}
      </main>
    </div>
  );
}

function DocumentEditor({
  mode,
  docId,
  isAdmin,
  onDone,
}: {
  mode: "new" | "edit";
  docId?: number;
  isAdmin: boolean;
  onDone: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const docQuery = useQuery({
    queryKey: ["admin", "kb", "doc", docId],
    queryFn: () => adminApi.kbGet(docId!),
    enabled: mode === "edit" && docId !== undefined,
  });

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [body, setBody] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (docQuery.data) {
      setTitle(docQuery.data.title);
      setCategory(docQuery.data.category ?? "");
      setBody(docQuery.data.body);
      setIsActive(docQuery.data.is_active);
    } else if (mode === "new") {
      setTitle("");
      setCategory("");
      setBody("");
      setIsActive(true);
    }
  }, [docQuery.data, mode, docId]);

  async function handleSave() {
    setBusy(true);
    try {
      if (mode === "new") {
        const created = await adminApi.kbCreate({ title, body, category: category || null });
        await queryClient.invalidateQueries({ queryKey: ["admin", "kb", "list"] });
        onDone(created.id);
      } else if (docId) {
        await adminApi.kbUpdate(docId, { title, body, category: category || null, is_active: isActive });
        await queryClient.invalidateQueries({ queryKey: ["admin", "kb", "list"] });
        await queryClient.invalidateQueries({ queryKey: ["admin", "kb", "doc", docId] });
      }
      setSavedAt(Date.now());
    } finally {
      setBusy(false);
    }
  }

  if (mode === "edit" && docQuery.isLoading) {
    return <div className="p-6 text-sm text-neutral-400">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h2 className="text-lg font-semibold">{mode === "new" ? "New document" : "Edit document"}</h2>
      {!isAdmin && (
        <p className="mt-1 text-xs text-amber-600">
          Read-only — editing the knowledge base requires the admin role.
        </p>
      )}

      <label className="mt-4 block text-xs font-medium text-neutral-600">Title</label>
      <input
        value={title}
        disabled={!isAdmin}
        onChange={(e) => setTitle(e.target.value)}
        className="mt-1 w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm disabled:bg-neutral-50"
      />

      <label className="mt-3 block text-xs font-medium text-neutral-600">Category</label>
      <input
        value={category}
        disabled={!isAdmin}
        onChange={(e) => setCategory(e.target.value)}
        className="mt-1 w-full rounded-lg border border-neutral-300 px-3 py-2 text-sm disabled:bg-neutral-50"
      />

      <label className="mt-3 block text-xs font-medium text-neutral-600">Body</label>
      <textarea
        value={body}
        disabled={!isAdmin}
        onChange={(e) => setBody(e.target.value)}
        rows={16}
        className="mt-1 w-full rounded-lg border border-neutral-300 p-3 font-mono text-xs disabled:bg-neutral-50"
      />

      {mode === "edit" && (
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isActive}
            disabled={!isAdmin}
            onChange={(e) => setIsActive(e.target.checked)}
          />
          Active (included in retrieval)
        </label>
      )}

      {isAdmin && (
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={busy || !title.trim() || !body.trim()}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {mode === "new" ? "Create" : "Save (re-embeds if body changed)"}
          </button>
          {savedAt && <span className="text-xs text-emerald-600">Saved.</span>}
        </div>
      )}
    </div>
  );
}
