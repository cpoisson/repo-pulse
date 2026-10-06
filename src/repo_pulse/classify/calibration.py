"""Calibration + evaluation primitives (numpy only)."""
from __future__ import annotations

import numpy as np


def softmax(logits: np.ndarray, T: float = 1.0) -> np.ndarray:
    z = logits / T
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def nll(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(np.log(p[np.arange(len(y)), y] + 1e-12)))


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    grid = np.exp(np.linspace(np.log(0.05), np.log(20), 200))
    return float(min(grid, key=lambda T: nll(softmax(logits, T), y)))


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    conf, pred = p.max(1), p.argmax(1)
    acc = pred == y
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(acc[m].mean() - conf[m].mean())
    return round(float(e), 4)


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[list]:
    conf, acc = p.max(1), p.argmax(1) == y
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            out.append([round(float(conf[m].mean()), 3), round(float(acc[m].mean()), 3), int(m.sum())])
    return out


def brier(p: np.ndarray, y: np.ndarray) -> float:
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1
    return round(float(np.mean(np.sum((p - oh) ** 2, 1))), 4)


def macro_f1(pred: np.ndarray, y: np.ndarray, n_classes: int) -> tuple[float, list[float]]:
    f1s = []
    for c in range(n_classes):
        tp = np.sum((pred == c) & (y == c))
        fp = np.sum((pred == c) & (y != c))
        fn = np.sum((pred != c) & (y == c))
        if tp + fp + fn == 0:
            continue  # class absent from both: skip
        f1s.append(2 * tp / (2 * tp + fp + fn))
    return round(float(np.mean(f1s)), 4), [round(float(x), 3) for x in f1s]


def confusion(pred: np.ndarray, y: np.ndarray, classes: list[str]) -> dict[str, dict[str, int]]:
    """rows: predicted, cols: true."""
    out = {c: {t: 0 for t in classes} for c in classes}
    for a, b in zip(pred, y):
        out[classes[a]][classes[b]] += 1
    return out


def threshold_for_precision(p: np.ndarray, y: np.ndarray, target: float) -> float:
    """Lowest confidence threshold whose accepted set reaches target precision (on calibration data)."""
    conf, ok = p.max(1), p.argmax(1) == y
    order = np.argsort(-conf)
    best = 1.01
    hits = 0
    for k, i in enumerate(order, 1):
        hits += ok[i]
        if hits / k >= target:
            best = float(conf[i])
    return round(best, 4)


def selective(p: np.ndarray, y: np.ndarray, thr: float) -> tuple[float, float | None]:
    keep = p.max(1) >= thr
    cov = float(keep.mean())
    prec = float((p.argmax(1)[keep] == y[keep]).mean()) if keep.any() else None
    return round(cov, 3), (round(prec, 3) if prec is not None else None)
