import { motion } from "motion/react";
import { useId, type ReactNode } from "react";
import { cx } from "../lib/cx";

export type TabItem<T extends string> = { value: T; label: ReactNode };

/** Underlined tab strip. The underline slides between tabs so the change
 * reads as one control moving, not two elements swapping. */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  const group = useId();

  // Arrow keys move between tabs (WAI-ARIA tabs pattern); only the active
  // tab sits in the Tab order.
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const index = items.findIndex((item) => item.value === value);
    const next = (index + step + items.length) % items.length;
    onChange(items[next].value);
    const buttons = e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons[next]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={handleKeyDown}
      className={cx("flex items-stretch gap-1", className)}
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.value)}
            className={cx(
              "relative inline-flex h-10 items-center gap-1.5 px-2 text-sm whitespace-nowrap transition-colors duration-150",
              active ? "font-medium text-ink" : "text-ink-3 hover:text-ink",
            )}
          >
            {item.label}
            {active && (
              <motion.span
                layoutId={`tab-underline-${group}`}
                transition={{ type: "spring", bounce: 0, duration: 0.3 }}
                className="absolute inset-x-2 -bottom-px h-0.5 bg-accent"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
