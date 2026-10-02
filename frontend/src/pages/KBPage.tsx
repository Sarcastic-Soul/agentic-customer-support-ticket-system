import { ArrowLeftIcon, BooksIcon, CheckIcon, LockSimpleIcon, PlusIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Button, EmptyState, ErrorState, Field, SkeletonRows, TextArea, TextInput } from "../components/ui";
import { adminApi, type KBDocumentDetail } from "../lib/admin-api";
import { getAgent } from "../lib/auth";
import { cx } from "../lib/cx";
import { errorMessage, humanize, relativeTime } from "../lib/format";

export function KBPage() {
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const isAdmin = getAgent()?.role === "admin";

  const listQuery = useQuery({
    queryKey: ["admin", "kb", "list"],
    queryFn: () => adminApi.kbList(),
  });

  return (
    <div className="flex h-full">
      <aside
        aria-label="Documents"
        className={cx(
          "flex w-full flex-col border-r border-rule bg-surface md:w-80 md:shrink-0",
          selectedId !== null && "hidden md:flex",
        )}
      >
        <div className="flex items-center justify-between gap-3 border-b border-rule px-4 py-4">
          <div>
            <h1 className="text-xl font-semibold">Knowledge base</h1>
            <p className="mt-0.5 text-xs text-ink-3">
              {listQuery.data ? `${listQuery.data.length} documents` : " "}
            </p>
          </div>
          {isAdmin && (
            <Button size="sm" variant="primary" icon={PlusIcon} onClick={() => setSelectedId("new")}>
              New
            </Button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {listQuery.isPending ? (
            <SkeletonRows rows={8} />
          ) : listQuery.isError ? (
            <ErrorState error={listQuery.error} onRetry={() => listQuery.refetch()} />
          ) : listQuery.data.length === 0 ? (
            <EmptyState icon={BooksIcon} title="No documents yet">
              {isAdmin ? "Add a policy or product document so the AI has something to answer from." : "An admin needs to add documents first."}
            </EmptyState>
          ) : (
            <ul className="divide-y divide-rule">
              {listQuery.data.map((doc) => {
                const selected = selectedId === doc.id;
                return (
                  <li key={doc.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(doc.id)}
                      aria-current={selected ? "true" : undefined}
                      className={cx(
                        "relative block w-full px-4 py-3 text-left transition-colors duration-100 hover:bg-paper",
                        selected && "bg-paper",
                      )}
                    >
                      {selected && <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-accent" />}
                      <span className={cx("block text-sm font-medium", doc.is_active ? "text-ink" : "text-ink-3")}>
                        {doc.title}
                      </span>
                      <span className="mt-1 flex items-center gap-2 text-xs text-ink-3">
                        <span>{doc.category ? humanize(doc.category) : "No category"}</span>
                        <span className="font-mono tabular">v{doc.version}</span>
                        {!doc.is_active && <span className="text-ochre">Not used by AI</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      <section className={cx("min-w-0 flex-1 overflow-y-auto", selectedId === null && "hidden md:block")}>
        {selectedId === "new" ? (
          <DocumentEditor
            key="new"
            mode="new"
            isAdmin={isAdmin}
            onDone={(id) => setSelectedId(id)}
            onBack={() => setSelectedId(null)}
          />
        ) : selectedId ? (
          <DocumentEditor
            key={selectedId}
            mode="edit"
            docId={selectedId}
            isAdmin={isAdmin}
            onDone={() => {}}
            onBack={() => setSelectedId(null)}
          />
        ) : (
          <div className="flex h-full items-center px-10">
            <div className="max-w-sm">
              <p className="font-display text-lg font-medium text-ink">Pick a document to read or edit it.</p>
              <p className="mt-2 text-sm text-ink-3">
                The AI answers policy and product questions only from active documents here. Saving a changed body
                re-indexes it for search.
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function DocumentEditor({
  mode,
  docId,
  isAdmin,
  onDone,
  onBack,
}: {
  mode: "new" | "edit";
  docId?: number;
  isAdmin: boolean;
  onDone: (id: number) => void;
  onBack: () => void;
}) {
  const docQuery = useQuery({
    queryKey: ["admin", "kb", "doc", docId],
    queryFn: () => adminApi.kbGet(docId!),
    enabled: mode === "edit" && docId !== undefined,
  });

  const back = (
    <button
      type="button"
      onClick={onBack}
      className="mb-3 inline-flex min-h-9 items-center gap-1.5 text-sm text-ink-3 hover:text-ink md:hidden"
    >
      <ArrowLeftIcon size={14} aria-hidden />
      All documents
    </button>
  );

  if (mode === "edit" && docQuery.isPending) {
    return (
      <div className="px-6 py-6">
        {back}
        <SkeletonRows rows={4} />
      </div>
    );
  }
  if (mode === "edit" && docQuery.isError) {
    return (
      <div className="px-6 py-6">
        {back}
        <ErrorState error={docQuery.error} onRetry={() => docQuery.refetch()} className="px-0" />
      </div>
    );
  }

  return <EditorForm mode={mode} doc={docQuery.data} isAdmin={isAdmin} onDone={onDone} back={back} />;
}

/** Fields start from the loaded document once; the parent keys the editor
 * by document id, so switching documents remounts rather than re-syncing. */
function EditorForm({
  mode,
  doc,
  isAdmin,
  onDone,
  back,
}: {
  mode: "new" | "edit";
  doc: KBDocumentDetail | undefined;
  isAdmin: boolean;
  onDone: (id: number) => void;
  back: ReactNode;
}) {
  const queryClient = useQueryClient();
  const docId = doc?.id;
  const [title, setTitle] = useState(doc?.title ?? "");
  const [category, setCategory] = useState(doc?.category ?? "");
  const [body, setBody] = useState(doc?.body ?? "");
  const [isActive, setIsActive] = useState(doc?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleSave() {
    setBusy(true);
    setSaved(false);
    setSaveError(null);
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
      setSaved(true);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // `doc` is the parent's live query data, so a refetch after saving clears this.
  const dirty =
    mode === "new" ||
    (doc &&
      (title !== doc.title ||
        category !== (doc.category ?? "") ||
        body !== doc.body ||
        isActive !== doc.is_active));

  return (
    <div className="mx-auto max-w-3xl px-5 py-6 sm:px-8">
      {back}
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-xl font-semibold">{mode === "new" ? "New document" : "Edit document"}</h2>
        {doc && (
          <p className="font-mono text-xs text-ink-3 tabular">
            v{doc.version} · updated {relativeTime(doc.updated_at)}
          </p>
        )}
      </div>
      {!isAdmin && (
        <p className="mt-3 inline-flex items-center gap-1.5 text-sm text-ink-3">
          <LockSimpleIcon size={15} aria-hidden />
          Read only. Editing needs the admin role.
        </p>
      )}

      <div className="mt-6 space-y-5">
        <Field label="Title" htmlFor="kb-title">
          <TextInput
            id="kb-title"
            value={title}
            disabled={!isAdmin}
            onChange={(e) => {
              setTitle(e.target.value);
              setSaved(false);
            }}
          />
        </Field>
        <Field label="Category" htmlFor="kb-category" hint="Optional. For example: returns, shipping, payments.">
          <TextInput
            id="kb-category"
            value={category}
            disabled={!isAdmin}
            onChange={(e) => {
              setCategory(e.target.value);
              setSaved(false);
            }}
            className="sm:max-w-xs"
          />
        </Field>
        <Field label="Body" htmlFor="kb-body" hint="Markdown. Headings are used to split the document for search.">
          <TextArea
            id="kb-body"
            value={body}
            disabled={!isAdmin}
            onChange={(e) => {
              setBody(e.target.value);
              setSaved(false);
            }}
            rows={18}
            className="font-mono text-[13px]"
          />
        </Field>

        {mode === "edit" && (
          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              checked={isActive}
              disabled={!isAdmin}
              onChange={(e) => {
                setIsActive(e.target.checked);
                setSaved(false);
              }}
              className="mt-0.5 size-4 accent-ink"
            />
            <span>
              <span className="font-medium text-ink">Active</span>
              <span className="block text-ink-3">The AI can use this document when answering.</span>
            </span>
          </label>
        )}
      </div>

      {isAdmin && (
        <div className="sticky bottom-0 -mx-5 mt-8 flex flex-wrap items-center gap-3 border-t border-rule bg-paper/95 px-5 py-3 sm:-mx-8 sm:px-8">
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={busy || !title.trim() || !body.trim() || !dirty}
          >
            {busy ? "Saving…" : mode === "new" ? "Create document" : "Save changes"}
          </Button>
          {saved && !busy && (
            <span role="status" className="inline-flex items-center gap-1.5 text-sm text-moss">
              <CheckIcon size={15} aria-hidden />
              Saved
            </span>
          )}
          {saveError && (
            <span role="alert" className="inline-flex items-center gap-1.5 text-sm text-accent-strong">
              <WarningCircleIcon size={15} aria-hidden />
              {saveError}
            </span>
          )}
          {mode === "edit" && !saved && !saveError && (
            <span className="text-xs text-ink-3">Changing the body re-indexes it for search.</span>
          )}
        </div>
      )}
    </div>
  );
}
