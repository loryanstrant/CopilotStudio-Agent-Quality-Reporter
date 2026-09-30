import type { ReactNode } from "react";

/**
 * A page title and the sentence or two under it that says what the page is for.
 *
 * It exists because that explainer paragraph was hand-rolled on every page and
 * three of them had picked up a `max-w-3xl` — 768px of text inside a 1536px
 * content column, so the copy wrapped at under half the width it had been
 * given while the table beneath it ran the full width. It read like a mistake
 * because it was one: the standard is that text uses the width it is given.
 *
 * So there is no width cap here. If one is ever wanted — a 1600px line of 14px
 * text is a long line to track back from — this is now the single place to put
 * it, rather than a number copied onto each page and diverging.
 */
export default function PageHeader({
  title,
  children,
  actions,
}: {
  title: string;
  /** The explainer paragraph. Rich content is fine — it is often part link. */
  children?: ReactNode;
  /** Optional controls that belong beside the title rather than below it. */
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          {title}
        </h1>
        {children && (
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{children}</p>
        )}
      </div>
      {actions}
    </div>
  );
}
