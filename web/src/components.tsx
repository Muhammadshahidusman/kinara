// Small shared pieces: status badge, KPI card with (i) popover, banners, charts, protected image.
import { useEffect, useId, useState, type ReactNode } from "react";
import { blobUrl, type AlertStatus, type SparkPoint } from "./api";
import { fmtDate, fmtN } from "./format";
import { useI18n } from "./i18n";

export function StatusBadge({ status }: { status: AlertStatus }) {
  const { t } = useI18n();
  return <span className={`badge ${status}`}>{t(status)}</span>;
}

export function Info({ children, label }: { children: ReactNode; label: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="info">
      <button type="button" className="info-btn" aria-expanded={open} aria-controls={id}
        aria-label={label} onClick={() => setOpen(!open)}>i</button>
      {open && <span role="dialog" id={id} className="popover" onClick={() => setOpen(false)}>{children}</span>}
    </span>
  );
}

export function Kpi({ value, label, sub, info, tag }: { value: string; label: string; sub?: string; info: ReactNode;
  tag?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label} <Info label={label}>{info}</Info></div>
      {sub && <div className="muted">{sub}</div>}
      {tag && <div className="tag-warn">{tag}</div>}
    </div>
  );
}

export function Banner({ kind, children }: { kind: "error" | "warn"; children: ReactNode }) {
  return <div className={`banner ${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

export function Skeleton({ h = 80 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} aria-hidden="true" />;
}

/** Image from a protected endpoint (needs the bearer token, so it can't be a plain <img src>). */
export function AuthImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let u: string | null = null;
    let live = true;
    blobUrl(path).then((x) => { u = x; if (live) setUrl(x); }).catch(() => live && setFailed(true));
    return () => { live = false; if (u) URL.revokeObjectURL(u); };
  }, [path]);
  if (failed) return null;
  return url ? <img src={url} alt={alt} className={className} /> : <Skeleton h={200} />;
}

/** Radar backscatter per pass: one series, 2 px line, 8 px markers, hover tooltip (dataviz mark specs). */
export function Sparkline({ points }: { points: SparkPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const vals = points.map((p) => p.vv_db).filter((v): v is number => v != null);
  if (vals.length < 2) return null;
  const W = 320, H = 96, L = 34, R = 8, T = 10, B = 22;
  const lo = Math.floor(Math.min(...vals) - 1), hi = Math.ceil(Math.max(...vals) + 1);
  const x = (i: number) => L + (i * (W - L - R)) / Math.max(1, points.length - 1);
  const y = (v: number) => T + ((hi - v) * (H - T - B)) / (hi - lo);
  const pts = points.map((p, i) => (p.vv_db == null ? null : [x(i), y(p.vv_db)] as const));
  const d = pts.filter(Boolean).map((p, i) => `${i ? "L" : "M"}${p![0].toFixed(1)},${p![1].toFixed(1)}`).join("");
  const hp = hover != null ? points[hover] : null;
  return (
    <figure className="spark">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Radar backscatter per Sentinel-1 pass"
        onMouseLeave={() => setHover(null)}>
        {[lo, hi].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" />
            <text x={L - 4} y={y(v) + 4} textAnchor="end" className="axis">{v} dB</text>
          </g>
        ))}
        <text x={L} y={H - 6} className="axis">{fmtDate(points[0].day)}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="axis">{fmtDate(points[points.length - 1].day)}</text>
        <path d={d} className="spark-line" />
        {pts.map((p, i) => p && (
          <g key={i} onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} tabIndex={0}>
            <circle cx={p[0]} cy={p[1]} r={12} fill="transparent" />
            <circle cx={p[0]} cy={p[1]} r={hover === i ? 5 : 4} className="spark-dot" />
          </g>
        ))}
        {hp && hover != null && pts[hover] && (
          <g transform={`translate(${Math.min(pts[hover]![0], W - 110)},${Math.max(pts[hover]![1] - 30, 2)})`}>
            <rect width="104" height="22" rx="4" className="tip-bg" />
            <text x="6" y="15" className="tip">{fmtDate(hp.day)}: {hp.vv_db?.toFixed(1)} dB</text>
          </g>
        )}
      </svg>
    </figure>
  );
}

/** Horizontal bars, one hue, values labelled at the bar end; the exposure table is the table view. */
export function Bars({ rows }: { rows: { label: string; value: number; sub?: string }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="bars" role="list">
      {rows.map((r, i) => (
        <div key={r.label + i} role="listitem" className="bar-row" onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)} title={r.sub ? `${r.label}: ${fmtN(r.value)} (${r.sub})` : undefined}>
          <span className="bar-label">{r.label}</span>
          <span className="bar-track">
            <span className={`bar ${hover === i ? "hot" : ""}`} style={{ width: `${(100 * r.value) / max}%` }} />
          </span>
          <span className="bar-value">{fmtN(r.value)}</span>
        </div>
      ))}
    </div>
  );
}
