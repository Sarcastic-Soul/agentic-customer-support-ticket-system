import {
  ArrowClockwiseIcon,
  EnvelopeSimpleIcon,
  GlobeSimpleIcon,
  MicrophoneIcon,
  WarningCircleIcon,
  WhatsappLogoIcon,
  type Icon,
} from "@phosphor-icons/react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cx } from "../lib/cx";
import { errorMessage, humanize, statusLabel } from "../lib/format";

/* ---------- buttons ---------- */

type ButtonVariant = "primary" | "secondary" | "quiet";
type ButtonSize = "sm" | "md";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-ink text-paper hover:bg-ink-2 active:translate-y-px disabled:bg-ink-4 disabled:text-paper",
  secondary:
    "border border-rule-strong bg-surface text-ink hover:border-ink-3 hover:bg-paper active:translate-y-px",
  quiet: "text-ink-2 hover:bg-sunk hover:text-ink",
};

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-xs",
  md: "h-9 gap-2 px-3.5 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  icon: IconComponent,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: Icon;
}) {
  return (
    <button
      type="button"
      {...rest}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-md font-medium transition-[background-color,border-color,color,transform] duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON_VARIANT[variant],
        BUTTON_SIZE[size],
        className,
      )}
    >
      {IconComponent && <IconComponent size={size === "sm" ? 14 : 16} aria-hidden />}
      {children}
    </button>
  );
}

/* ---------- form fields ---------- */

const FIELD =
  "rounded-md border border-rule-strong bg-surface px-3 text-sm text-ink placeholder:text-ink-4 transition-colors duration-150 hover:border-ink-4 focus:border-ink focus:outline-none focus-visible:outline-none disabled:bg-sunk disabled:text-ink-3";

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(FIELD, "h-9 w-full", className)} />;
}

export function TextArea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx(FIELD, "w-full py-2 leading-relaxed", className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(FIELD, "select-field h-8 w-auto pr-7! text-xs", className)}>
      {children}
    </select>
  );
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: ReactNode;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-ink-2">
        {label}
      </label>
      <div className="mt-1.5">{children}</div>
      {hint && <p className="mt-1.5 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

/* ---------- status marks ---------- */

const STATUS_TONE: Record<string, { dot: string; text: string; pulse?: boolean }> = {
  new: { dot: "bg-slate", text: "text-slate" },
  ai_working: { dot: "bg-ink", text: "text-ink", pulse: true },
  escalated: { dot: "bg-accent", text: "text-accent-strong" },
  human_working: { dot: "bg-ochre", text: "text-ochre" },
  closed: { dot: "bg-ink-4", text: "text-ink-3" },
  queued: { dot: "bg-accent", text: "text-accent-strong" },
  claimed: { dot: "bg-ochre", text: "text-ochre" },
  resolved: { dot: "bg-moss", text: "text-moss" },
  returned_to_ai: { dot: "bg-ink", text: "text-ink" },
};

export function StatusMark({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? { dot: "bg-ink-4", text: "text-ink-3" };
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap", tone.text)}>
      <span aria-hidden className={cx("size-1.5 rounded-[1px]", tone.dot, tone.pulse && "pulse-dot")} />
      {statusLabel(status)}
    </span>
  );
}

const PRIORITY_STYLE: Record<string, string> = {
  P1: "bg-accent text-on-accent",
  P2: "border border-accent text-accent-strong",
  P3: "border border-rule-strong text-ink-2",
  P4: "text-ink-3",
};

export function PriorityMark({ priority }: { priority: string }) {
  return (
    <span
      title={`Priority ${priority.slice(1)}`}
      className={cx(
        "inline-flex h-5 min-w-7 items-center justify-center rounded-[3px] px-1 font-mono text-[11px] font-medium",
        PRIORITY_STYLE[priority] ?? "text-ink-3",
      )}
    >
      {priority}
    </span>
  );
}

const CHANNEL_ICON: Record<string, Icon> = {
  web: GlobeSimpleIcon,
  whatsapp: WhatsappLogoIcon,
  email: EnvelopeSimpleIcon,
  voice: MicrophoneIcon,
};

const CHANNEL_LABEL: Record<string, string> = {
  web: "Web chat",
  whatsapp: "WhatsApp",
  email: "Email",
  voice: "Voice",
};

export function ChannelMark({ channel, compact = false }: { channel: string; compact?: boolean }) {
  const IconComponent = CHANNEL_ICON[channel] ?? GlobeSimpleIcon;
  const label = CHANNEL_LABEL[channel] ?? humanize(channel);
  return (
    <span className="inline-flex items-center gap-1.5 text-ink-2" title={label}>
      <IconComponent size={15} aria-hidden className="shrink-0 text-ink-3" />
      {compact ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </span>
  );
}

/* ---------- page states ---------- */

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-[3px] bg-sunk", className)} />;
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="divide-y divide-rule" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3">
          <Skeleton className="h-3.5 w-16" />
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-3.5 flex-1" />
          <Skeleton className="h-3.5 w-10" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  icon: IconComponent,
  title,
  children,
  className,
}: {
  icon?: Icon;
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-col items-start gap-2 px-6 py-10 text-left", className)}>
      {IconComponent && <IconComponent size={22} aria-hidden className="text-ink-4" />}
      <p className="font-display text-base font-medium text-ink">{title}</p>
      {children && <div className="max-w-sm text-sm text-ink-3">{children}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div role="alert" className={cx("flex items-start gap-3 px-6 py-8", className)}>
      <WarningCircleIcon size={20} aria-hidden className="mt-0.5 shrink-0 text-accent" />
      <div>
        <p className="text-sm font-medium text-ink">Could not load this.</p>
        <p className="mt-0.5 text-sm text-ink-3">{errorMessage(error)}</p>
        {onRetry && (
          <Button size="sm" className="mt-3" icon={ArrowClockwiseIcon} onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </div>
  );
}

/** Small section heading used inside panels. Sentence case, not caps. */
export function PanelHeading({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <h3 className="font-display text-[13px] font-semibold text-ink">{children}</h3>
      {aside && <div className="text-xs text-ink-3">{aside}</div>}
    </div>
  );
}
