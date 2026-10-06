import React from "react";
import { AbsoluteFill, Composition, Html5Audio, interpolate, Sequence, staticFile } from "remotion";
import { C, FPS, s } from "./theme";
import { Agents, Frugal, Grounded, Measured, Outro, Pipeline, Problem, Results, Showcase, Title } from "./scenes";

type Item = { sec: number; el: (dur: number) => React.ReactNode };

// YouTube cut: ~71 s, every scene/slide on screen for at least ~4 s.
const VIDEO: Item[] = [
  { sec: 4.5, el: (d) => <Title dur={d} /> },
  { sec: 6.5, el: (d) => <Problem dur={d} /> },
  { sec: 9.5, el: (d) => <Pipeline dur={d} /> },
  { sec: 5.6, el: (d) => <Showcase dur={d} src="trl-summary" kicker="The deck" caption="Executive summary" origin="0% 0%" zoom={1.7} /> },
  { sec: 5.6, el: (d) => <Showcase dur={d} src="trl-scorecard" kicker="The deck" caption="Scorecard" origin="0% 0%" zoom={1.7} /> },
  { sec: 5.6, el: (d) => <Showcase dur={d} src="trl-p1" kicker="The deck" caption="Improvement plan" origin="0% 10%" zoom={1.6} /> },
  { sec: 5.0, el: (d) => <Grounded dur={d} /> },
  { sec: 5.5, el: (d) => <Measured dur={d} /> },
  { sec: 5.0, el: (d) => <Frugal dur={d} /> },
  { sec: 6.5, el: (d) => <Results dur={d} /> },
  { sec: 6.5, el: (d) => <Agents dur={d} /> },
  { sec: 5.0, el: (d) => <Outro dur={d} /> },
];

// README GIF: ~21 s loop, slower than the video, no audio.
const GIF: Item[] = [
  { sec: 3.0, el: (d) => <Title dur={d} /> },
  { sec: 6.5, el: (d) => <Pipeline dur={d} step={26} /> },
  { sec: 3.8, el: (d) => <Showcase dur={d} src="trl-summary" still kicker="The deck" caption="Executive summary" /> },
  { sec: 3.8, el: (d) => <Showcase dur={d} src="trl-scorecard" still kicker="The deck" caption="Scorecard" /> },
  { sec: 3.8, el: (d) => <Showcase dur={d} src="trl-p1" still kicker="The deck" caption="Improvement plan" /> },
];

const total = (items: Item[]) => items.reduce((a, x) => a + s(x.sec), 0);

const Timeline: React.FC<{ items: Item[]; music?: boolean }> = ({ items, music }) => {
  let at = 0;
  const dur = total(items);
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {items.map((x, i) => {
        const d = s(x.sec);
        const seq = <Sequence key={i} from={at} durationInFrames={d}>{x.el(d)}</Sequence>;
        at += d;
        return seq;
      })}
      {music && (
        <Html5Audio src={staticFile("music.wav")}
          volume={(f) => interpolate(f, [0, 20, dur - 75, dur], [0, 0.85, 0.85, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
      )}
    </AbsoluteFill>
  );
};

export const Root: React.FC = () => (
  <>
    <Composition id="RepoPulse" component={() => <Timeline items={VIDEO} music />} durationInFrames={total(VIDEO)} fps={FPS} width={1920} height={1080} />
    <Composition id="ReadmeGif" component={() => <Timeline items={GIF} />} durationInFrames={total(GIF)} fps={FPS} width={1920} height={1080} />
  </>
);
