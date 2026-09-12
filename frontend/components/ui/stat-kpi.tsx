type StatKPIProps = {
  label: string;
  value: string | number;
  badge?: string;
  detail?: string;
  variant?: "default" | "emerald" | "amber" | "rose" | "indigo" | "sky" | "purple";
  className?: string;
};

const VARIANT_STYLES = {
  default: {
    container: "border-slate-200/80 bg-white",
    badge: "bg-slate-900 text-white",
    label: "text-slate-500",
    value: "text-slate-950",
  },
  emerald: {
    container: "border-emerald-500/20 bg-emerald-50/70",
    badge: "bg-emerald-600 text-white",
    label: "text-emerald-800",
    value: "text-emerald-950",
  },
  amber: {
    container: "border-amber-500/20 bg-amber-50/70",
    badge: "bg-amber-600 text-white",
    label: "text-amber-800",
    value: "text-amber-950",
  },
  rose: {
    container: "border-rose-500/20 bg-rose-50/70",
    badge: "bg-rose-600 text-white",
    label: "text-rose-800",
    value: "text-rose-950",
  },
  indigo: {
    container: "border-indigo-500/20 bg-indigo-50/70",
    badge: "bg-indigo-600 text-white",
    label: "text-indigo-800",
    value: "text-indigo-950",
  },
  sky: {
    container: "border-sky-500/20 bg-sky-50/70",
    badge: "bg-sky-600 text-white",
    label: "text-sky-800",
    value: "text-slate-950",
  },
  purple: {
    container: "border-purple-500/20 bg-purple-50/70",
    badge: "bg-purple-600 text-white",
    label: "text-purple-800",
    value: "text-purple-950",
  },
};

export function StatKPI({
  label,
  value,
  badge,
  detail,
  variant = "default",
  className = "",
}: StatKPIProps) {
  const styles = VARIANT_STYLES[variant];

  return (
    <div
      className={`flex items-center gap-3 rounded-xl border p-3.5 shadow-2xs ${styles.container} ${className}`}
    >
      {badge && (
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-mono font-bold shadow-xs ${styles.badge}`}
        >
          {badge}
        </span>
      )}
      <div>
        <p className={`text-[10px] font-bold uppercase tracking-wider ${styles.label}`}>
          {label}
        </p>
        <p className={`text-xs font-black sm:text-sm ${styles.value}`}>{value}</p>
        {detail && <p className="mt-0.5 text-[10px] text-slate-400">{detail}</p>}
      </div>
    </div>
  );
}
