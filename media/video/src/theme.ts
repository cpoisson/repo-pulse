import { loadFont } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

export const { fontFamily } = loadFont("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin"] });
export const { fontFamily: mono } = loadMono("normal", { weights: ["400", "600"], subsets: ["latin"] });

// Same palette as the generated decks, so the video and the product look like one thing.
export const C = {
  bg: "#f4f3ee",
  paper: "#fbfaf7",
  ink: "#0b0b0b",
  ink2: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  blue: "#2a78d6",
  orange: "#eb6834",
  green: "#1baf7a",
  gray: "#a9a79f",
  red: "#d03b3b",
  good: "#0ca30c",
};

export const FPS = 30;
export const s = (sec: number) => Math.round(sec * FPS);
