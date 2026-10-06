import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, fontFamily, mono } from "./theme";

/** Fade + rise in at `delay` frames, optional fade out before `outAt`. */
export const Reveal: React.FC<{ delay?: number; outAt?: number; y?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({
  delay = 0, outAt, y = 24, children, style,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - delay, fps, config: { damping: 200, mass: 0.8 } });
  const out = outAt === undefined ? 1 : interpolate(f, [outAt - 10, outAt], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <div style={{ opacity: p * out, transform: `translateY(${(1 - p) * y}px)`, ...style }}>{children}</div>;
};

/** Scene wrapper: background + gentle global fade in/out. */
export const Scene: React.FC<{ dur: number; children: React.ReactNode; bg?: string }> = ({ dur, children, bg = C.bg }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 8, dur - 8, dur], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", inset: 0, background: bg, fontFamily, color: C.ink, opacity: o, overflow: "hidden" }}>
      {children}
    </div>
  );
};

export const Kicker: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = C.muted }) => (
  <div style={{ fontSize: 26, letterSpacing: "0.14em", textTransform: "uppercase", color, fontWeight: 600 }}>{children}</div>
);

/** Metro line: stations drawn progressively; `active` index highlighted. */
export const Metro: React.FC<{
  stations: { label: string; sub?: string; color: string }[]; start?: number; step?: number; width?: number; active?: number;
}> = ({ stations, start = 0, step = 20, width = 1500, active }) => {
  const f = useCurrentFrame();
  const n = stations.length;
  const gap = width / (n - 1);
  const lineP = interpolate(f, [start, start + step * (n - 1)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  return (
    <div style={{ position: "relative", width, height: 260 }}>
      <div style={{ position: "absolute", left: 0, top: 58, height: 10, borderRadius: 5, background: C.grid, width }} />
      <div style={{ position: "absolute", left: 0, top: 58, height: 10, borderRadius: 5, width: width * lineP,
        background: `linear-gradient(90deg, ${stations.map((s, i) => `${s.color} ${(i / (n - 1)) * 100}%`).join(",")})` }} />
      {stations.map((st, i) => {
        const appear = start + i * step;
        const p = interpolate(f, [appear, appear + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const isActive = active === undefined ? false : active === i;
        const size = isActive ? 56 : 44;
        return (
          <div key={i} style={{ position: "absolute", left: i * gap, top: 0, transform: "translateX(-50%)", textAlign: "center", width: 320 }}>
            <div style={{ margin: "0 auto", marginTop: 63 - size / 2, width: size, height: size, borderRadius: "50%", background: p > 0.5 ? st.color : C.paper,
              border: `8px solid ${st.color}`, transform: `scale(${0.4 + 0.6 * p})`, opacity: p, boxShadow: isActive ? `0 0 0 8px ${C.bg}, 0 0 0 14px ${st.color}` : "none" }} />
            <div style={{ marginTop: 26, fontSize: 40, fontWeight: 750, opacity: p, color: C.ink }}>{st.label}</div>
            {st.sub && <div style={{ marginTop: 6, fontSize: 25, color: C.ink2, opacity: p }}>{st.sub}</div>}
          </div>
        );
      })}
    </div>
  );
};

/** Real deck slide, slow push-in, soft shadow. */
export const SlideShot: React.FC<{ src: string; dur: number; width?: number; from?: number; to?: number; origin?: string; hold?: number }> = ({
  src, dur, width = 1440, from = 1.0, to = 1.05, origin = "50% 40%", hold = 0,
}) => {
  const f = useCurrentFrame();
  // with `hold`, show the whole slide first, then ease into the region that matters
  const k = hold
    ? interpolate(f, [hold, hold + 40], [from, to], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) })
    : interpolate(f, [0, dur], [from, to], { extrapolateRight: "clamp" });
  const o = interpolate(f, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ width, height: (width * 9) / 16, borderRadius: 18, overflow: "hidden", opacity: o,
      boxShadow: "0 30px 80px rgba(0,0,0,0.18), 0 0 0 1px rgba(0,0,0,0.06)", background: C.paper }}>
      <Img src={staticFile(`slides/${src}.png`)} style={{ width: "100%", height: "100%", transform: `scale(${k})`, transformOrigin: origin }} />
    </div>
  );
};

export const Chip: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = C.blue }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 12, padding: "10px 22px", borderRadius: 999, background: C.paper,
    border: `2px solid ${color}`, fontSize: 30, fontWeight: 650, color: C.ink }}>
    <i style={{ width: 14, height: 14, borderRadius: 7, background: color, display: "inline-block" }} />{children}
  </span>
);

export const Counter: React.FC<{ to: number; start: number; dur?: number; fmt?: (n: number) => string; style?: React.CSSProperties }> = ({
  to, start, dur = 30, fmt = (n) => Math.round(n).toLocaleString("en-US"), style,
}) => {
  const f = useCurrentFrame();
  const v = interpolate(f, [start, start + dur], [0, to], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return <span style={{ fontVariantNumeric: "tabular-nums", ...style }}>{fmt(v)}</span>;
};

export const Code: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ fontFamily: mono, fontSize: 30, background: "#16181d", color: "#e8e6df", padding: "22px 30px", borderRadius: 14, ...style }}>{children}</div>
);
