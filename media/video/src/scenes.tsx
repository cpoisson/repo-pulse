import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, Easing } from "remotion";
import { C, mono } from "./theme";
import { Chip, Code, Counter, Kicker, Metro, Reveal, Scene, SlideShot } from "./ui";

const center: React.CSSProperties = { position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" };
const pad: React.CSSProperties = { position: "absolute", inset: 0, padding: "80px 150px", display: "flex", flexDirection: "column", justifyContent: "center" };

export const PIPELINE = [
  { label: "Collect", sub: "GitHub · git · PyPI", color: C.blue },
  { label: "Measure", sub: "90 d vs prior 90 d", color: C.blue },
  { label: "Classify", sub: "measured model", color: C.green },
  { label: "Narrate", sub: "numbers checked", color: C.orange },
  { label: "Deck", sub: "one HTML file", color: C.ink },
];

export const Title: React.FC<{ dur: number; tagline?: string }> = ({ dur, tagline = "Your repo's health, in one deck." }) => {
  const f = useCurrentFrame();
  const w = interpolate(f, [6, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  return (
    <Scene dur={dur}>
      <div style={center}>
        <Reveal delay={4}><div style={{ fontSize: 150, fontWeight: 800, letterSpacing: "-0.03em" }}>repo<span style={{ color: C.blue }}>-</span>pulse</div></Reveal>
        <div style={{ width: 900 * w, height: 10, borderRadius: 5, marginTop: 18,
          background: `linear-gradient(90deg, ${C.blue}, ${C.green} 50%, ${C.orange})` }} />
        <Reveal delay={22}><div style={{ marginTop: 40, fontSize: 46, color: C.ink2, fontWeight: 500 }}>{tagline}</div></Reveal>
      </div>
    </Scene>
  );
};

export const Problem: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    <div style={center}>
      <Reveal delay={0}><Kicker>huggingface/trl, today</Kicker></Reveal>
      <div style={{ display: "flex", gap: 120, marginTop: 40 }}>
        {[["issues", 2655, 6], ["pull requests", 4737, 16], ["PRs merged in 90 days", 601, 26]].map(([lab, n, d]) => (
          <Reveal key={lab as string} delay={d as number}>
            <div style={{ textAlign: "center" }}>
              <Counter to={n as number} start={d as number} dur={36} style={{ fontSize: 128, fontWeight: 800, letterSpacing: "-0.02em" }} />
              <div style={{ fontSize: 34, color: C.ink2, marginTop: 4 }}>{lab}</div>
            </div>
          </Reveal>
        ))}
      </div>
      <Reveal delay={70}><div style={{ marginTop: 80, fontSize: 60, fontWeight: 700 }}>What should you act on?</div></Reveal>
    </div>
  </Scene>
);

export const Pipeline: React.FC<{ dur: number; step?: number }> = ({ dur, step = 34 }) => (
  <Scene dur={dur}>
    <div style={pad}>
      <Reveal><Kicker>How it works</Kicker></Reveal>
      <Reveal delay={6}><div style={{ fontSize: 72, fontWeight: 800, marginTop: 12, letterSpacing: "-0.015em" }}>Five steps. One deck.</div></Reveal>
      <div style={{ marginTop: 110, marginLeft: 110 }}><Metro stations={PIPELINE} start={30} step={step} width={1400} /></div>
    </div>
  </Scene>
);

export const Showcase: React.FC<{ dur: number; src: string; kicker: string; caption: string; origin?: string; zoom?: number; still?: boolean }> = ({ dur, src, kicker, caption, origin, zoom, still }) => (
  <Scene dur={dur}>
    <div style={{ position: "absolute", left: 110, top: 70 }}>
      <Reveal><Kicker color={C.blue}>{kicker}</Kicker></Reveal>
      <Reveal delay={5}><div style={{ fontSize: 50, fontWeight: 750, marginTop: 6 }}>{caption}</div></Reveal>
    </div>
    <div style={{ position: "absolute", left: (1920 - 1440) / 2, top: 222 }}>
      <SlideShot src={src} dur={dur} width={1440} origin={origin} to={zoom ?? (still ? 1.0 : 1.05)} hold={zoom ? 30 : 0} />
    </div>
  </Scene>
);

const Principle: React.FC<{ n: string; title: string; children: React.ReactNode }> = ({ n, title, children }) => (
  <div style={pad}>
    <Reveal><Kicker color={C.orange}>Principle {n}</Kicker></Reveal>
    <Reveal delay={6}><div style={{ fontSize: 84, fontWeight: 800, marginTop: 10, letterSpacing: "-0.015em" }}>{title}</div></Reveal>
    <div style={{ marginTop: 70 }}>{children}</div>
  </div>
);

export const Grounded: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const strike = interpolate(f, [62, 78], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Scene dur={dur}>
      <Principle n="1" title="Every number is checked.">
        <Reveal delay={20}>
          <Code>
            <div style={{ fontSize: 44 }}>"<b style={{ color: "#7fd6a8" }}>1.5%</b> replied in 7 days"  <span style={{ color: "#7fd6a8" }}>✓ kept</span></div>
          </Code>
        </Reveal>
        <Reveal delay={48}>
          <Code style={{ marginTop: 24, position: "relative" }}>
            <div style={{ fontSize: 44 }}>"<b style={{ color: "#ff9a8a" }}>45%</b> replied in 7 days"  <span style={{ color: "#ff9a8a" }}>✗ dropped</span></div>
            <div style={{ position: "absolute", left: 24, right: 24, top: 52, height: 4, background: "#ff9a8a", transformOrigin: "left", transform: `scaleX(${strike})` }} />
          </Code>
        </Reveal>
      </Principle>
    </Scene>
  );
};

export const Measured: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const bars = [
    { lab: "zero-shot", v: 0.14, c: C.gray },
    { lab: "local, free", v: 0.64, c: C.blue },
    { lab: "TypeSafe Jev", v: 0.72, c: C.green },
  ];
  const W = 1100;
  return (
    <Scene dur={dur}>
      <Principle n="2" title="Models are measured, not assumed.">
        <Reveal delay={14}><div style={{ marginBottom: 30 }}><Kicker>Issue-theme accuracy · TRL</Kicker></div></Reveal>
        <div style={{ position: "relative", width: W + 420 }}>
          {bars.map((b, i) => {
            const p = interpolate(f, [24 + i * 12, 54 + i * 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
            return (
              <div key={b.lab} style={{ display: "flex", alignItems: "center", marginBottom: 26 }}>
                <div style={{ width: 400, fontSize: 32, color: C.ink2 }}>{b.lab}</div>
                <div style={{ height: 54, width: W * b.v * p, background: b.c, borderRadius: 8 }} />
                <div style={{ marginLeft: 18, fontSize: 36, fontWeight: 750, opacity: p }}>{(b.v * p).toFixed(2)}</div>
              </div>
            );
          })}
          <Reveal delay={70} style={{ position: "absolute", left: 400 + W * 0.7, top: -20, bottom: 0 }}>
            <div style={{ height: 270, borderLeft: `4px dashed ${C.orange}` }} />
            <div style={{ fontSize: 26, color: C.orange, fontWeight: 700, marginLeft: -40 }}>gate 0.70</div>
          </Reveal>
        </div>
      </Principle>
    </Scene>
  );
};

export const Frugal: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    <Principle n="3" title="Free by default.">
      <div style={{ display: "flex", gap: 40 }}>
        {[
          { k: "local models", t: "0 tokens", c: C.blue, delay: 18 },
          { k: "Jev, opt-in", t: "$0.05 / 1k issues", c: C.green, delay: 34 },
          { k: "narrative", t: "~2k tokens", c: C.orange, delay: 50 },
        ].map((x) => (
          <Reveal key={x.k} delay={x.delay}>
            <div style={{ width: 500, padding: "34px 36px", background: C.paper, borderRadius: 18, borderTop: `8px solid ${x.c}`, boxShadow: "0 12px 40px rgba(0,0,0,0.06)" }}>
              <div style={{ fontSize: 34, color: C.ink2, fontWeight: 600 }}>{x.k}</div>
              <div style={{ fontSize: 54, fontWeight: 800, marginTop: 14, whiteSpace: "nowrap" }}>{x.t}</div>
            </div>
          </Reveal>
        ))}
      </div>
    </Principle>
  </Scene>
);

export const Results: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    <div style={pad}>
      <Reveal><Kicker>Three real projects</Kicker></Reveal>
      <Reveal delay={6}><div style={{ fontSize: 70, fontWeight: 800, marginTop: 10 }}>Three different stories.</div></Reveal>
      <div style={{ display: "flex", gap: 36, marginTop: 70 }}>
        {[
          { r: "huggingface/speech-to-speech", h: "One person does 95% of merges.", c: C.blue, d: 20 },
          { r: "huggingface/lerobot", h: "324 PRs waiting for review.", c: C.green, d: 40 },
          { r: "huggingface/trl", h: "External PRs merged: 18%, was 39%.", c: C.orange, d: 60 },
        ].map((x) => (
          <Reveal key={x.r} delay={x.d}>
            <div style={{ width: 520, height: 300, padding: 40, background: C.paper, borderRadius: 18, borderLeft: `8px solid ${x.c}`, boxShadow: "0 12px 40px rgba(0,0,0,0.06)" }}>
              <div style={{ fontFamily: mono, fontSize: 25, color: C.ink2 }}>{x.r}</div>
              <div style={{ fontSize: 52, fontWeight: 750, marginTop: 26, lineHeight: 1.2 }}>{x.h}</div>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  </Scene>
);

export const Agents: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    <div style={pad}>
      <Reveal><Kicker>Agent-agnostic</Kicker></Reveal>
      <Reveal delay={6}><div style={{ fontSize: 76, fontWeight: 800, marginTop: 10 }}>Runs with any agent.</div></Reveal>
      <div style={{ display: "flex", gap: 22, marginTop: 60, flexWrap: "wrap" }}>
        <Reveal delay={18}><Chip color={C.ink}>pi</Chip></Reveal>
        <Reveal delay={26}><Chip color={C.blue}>codex</Chip></Reveal>
        <Reveal delay={34}><Chip color={C.green}>claude</Chip></Reveal>
      </div>
      <Reveal delay={62}>
        <Code style={{ marginTop: 70, fontSize: 32 }}>
          <span style={{ color: "#9aa0a6" }}># every Monday, 06:00</span><br />
          0 6 * * 1  AGENT=codex scripts/run-edition.sh configs/trl.yaml
        </Code>
      </Reveal>
    </div>
  </Scene>
);

export const Outro: React.FC<{ dur: number }> = ({ dur }) => (
  <Scene dur={dur}>
    <div style={center}>
      <Reveal><div style={{ fontSize: 120, fontWeight: 800, letterSpacing: "-0.03em" }}>repo<span style={{ color: C.blue }}>-</span>pulse</div></Reveal>
      <Reveal delay={14}><div style={{ fontSize: 48, marginTop: 24, color: C.ink2 }}>Know where you stand. Know what's next.</div></Reveal>
    </div>
  </Scene>
);

export const Fill: React.FC = () => <AbsoluteFill style={{ background: C.bg }} />;
