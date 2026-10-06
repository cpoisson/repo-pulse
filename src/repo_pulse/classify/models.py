"""Classifier adapters for the bake-off. Each returns raw log-scores (n x C) per field; calibration happens later.

Zero-shot adapters ignore training data. Supervised adapters train on the calibration split.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

import numpy as np

EPS = 1e-6


def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


@dataclass
class Result:
    scores: dict[str, np.ndarray | None]  # field -> (n, C) log-scores
    seconds: float
    tokens: int = 0
    cost_usd: float = 0.0
    note: str = ""
    supervised: bool = False
    extra: dict = field(default_factory=dict)


class Base:
    name = "base"
    fields = ("type", "theme")
    supervised = False
    api = False          # True for paid/remote models; excluded in `classifier: local` mode

    def available(self) -> tuple[bool, str]:
        return True, ""

    def score(self, texts: list[str], labels: dict[str, dict[str, str]]) -> dict[str, np.ndarray | None]:
        raise NotImplementedError

    # supervised models override fit/predict instead of score
    def fit(self, texts, y: dict[str, list[str]], labels): ...


# --------------------------------------------------------------------------- rules baseline
TYPE_KEYWORDS = {
    "bug": r"error|bug|fail|crash|traceback|exception|broken|doesn't|does not|cannot|can't|silently|wrong|issue",
    "enhancement": r"feature|support|add |would be|proposal|request|improve|refactor|idea|design",
    "question": r"\?|how to|how can|is it possible|can i|question|help",
}


STOP = set("""a an and any are as at be by for from in into is it its of on or other the their to via with without
when which while this that these those not no more less about also than then""".split())


def theme_patterns(labels: dict[str, str]) -> dict[str, str]:
    """Keyword regex per theme, derived from the taxonomy's own keys and descriptions so the baseline is repo-agnostic."""
    out = {}
    for key, desc in labels.items():
        if key == "other":
            continue
        words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9+._-]{2,}", f"{key.replace('_', ' ')} {desc}")}
        words = sorted(w.strip("._-") for w in words if w.lower() not in STOP)
        out[key] = "|".join(re.escape(w) for w in words if len(w) > 2)
    return out


class Rules(Base):
    name = "rules"

    def score(self, texts, labels):
        out = {}
        for f, kw in (("type", TYPE_KEYWORDS), ("theme", theme_patterns(labels["theme"]))):
            classes = list(labels[f])
            m = np.zeros((len(texts), len(classes)))
            for i, t in enumerate(texts):
                tl = t.lower()
                for j, c in enumerate(classes):
                    pat = kw.get(c)
                    m[i, j] = len(re.findall(pat, tl)) if pat else 0.0
            if "other" in classes:
                m[:, classes.index("other")] = 0.5
            out[f] = np.log(m + 0.1)
        return out


# --------------------------------------------------------------------------- GLiClass (zero-shot)
class GLiClass(Base):
    def __init__(self, repo: str):
        self.repo = repo
        self.name = repo.split("/")[-1]

    def score(self, texts, labels):
        from gliclass import GLiClassModel, ZeroShotClassificationPipeline
        from transformers import AutoTokenizer

        model = GLiClassModel.from_pretrained(self.repo)
        tok = AutoTokenizer.from_pretrained(self.repo, add_prefix_space=True)
        pipe = ZeroShotClassificationPipeline(model, tok, classification_type="multi-label", device=_device())
        out = {}
        for f in ("type", "theme"):
            classes = list(labels[f])
            names = [labels[f][c] for c in classes]  # descriptions as label text
            m = np.zeros((len(texts), len(classes)))
            for i, t in enumerate(texts):
                res = {r["label"]: r["score"] for r in pipe(t, names, threshold=0.0)[0]}
                m[i] = [res.get(n, 0.0) for n in names]
            out[f] = np.log(m + EPS)
        return out


# --------------------------------------------------------------------------- NLI zero-shot
class NLIZeroShot(Base):
    def __init__(self, repo: str):
        self.repo = repo
        self.name = repo.split("/")[-1]

    def score(self, texts, labels):
        from transformers import pipeline

        pipe = pipeline("zero-shot-classification", model=self.repo, device=_device())
        out = {}
        for f in ("type", "theme"):
            classes = list(labels[f])
            names = [labels[f][c] for c in classes]
            m = np.zeros((len(texts), len(classes)))
            res = pipe(texts, names, hypothesis_template="This GitHub issue is about: {}", multi_label=False, batch_size=16)
            for i, r in enumerate(res):
                d = dict(zip(r["labels"], r["scores"]))
                m[i] = [d[n] for n in names]
            out[f] = np.log(m + EPS)
        return out


# --------------------------------------------------------------------------- fine-tuned issue-type model (type only)
class IssueTypeFT(Base):
    fields = ("type",)
    CARD_ORDER = ["bug", "enhancement", "question"]  # "classifies GitHub issues as 'bug', 'enhancement' or 'question'"

    def __init__(self, repo: str = "aieng-lab/ModernBERT-base_issue-type"):
        self.repo = repo
        self.name = repo.split("/")[-1]

    def score(self, texts, labels):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(self.repo)
        model = AutoModelForSequenceClassification.from_pretrained(self.repo).to(_device()).eval()
        id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
        if all(v.startswith("label_") for v in id2label.values()):
            id2label = dict(enumerate(self.CARD_ORDER))  # config has generic names; order from the model card
        classes = list(labels["type"])
        logits = []
        with torch.no_grad():
            for i in range(0, len(texts), 16):
                enc = tok(texts[i:i + 16], truncation=True, max_length=256, padding=True, return_tensors="pt").to(_device())
                logits.append(model(**enc).logits.float().cpu().numpy())
        lg = np.concatenate(logits)
        # map model labels onto ours (bug/enhancement/question, possibly with synonyms)
        alias = {"feature": "enhancement", "feature request": "enhancement", "improvement": "enhancement"}
        cols = []
        for c in classes:
            j = next((j for j, n in id2label.items() if alias.get(n, n) == c), None)
            cols.append(lg[:, j] if j is not None else np.full(len(texts), -20.0))
        return {"type": np.stack(cols, 1), "theme": None}


# --------------------------------------------------------------------------- supervised: embeddings + logistic regression
class EmbedLR(Base):
    supervised = True

    def __init__(self, repo: str = "BAAI/bge-small-en-v1.5"):
        self.repo = repo
        self.name = f"{repo.split('/')[-1]}+LR"
        self._enc = None

    def _embed(self, texts):
        from sentence_transformers import SentenceTransformer

        if self._enc is None:
            self._enc = SentenceTransformer(self.repo, device=_device())
        return self._enc.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)

    def fit_predict(self, train_texts, y, test_texts, labels):
        from sklearn.linear_model import LogisticRegression

        Xtr, Xte = self._embed(train_texts), self._embed(test_texts)
        out = {}
        for f in ("type", "theme"):
            classes = list(labels[f])
            clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced").fit(Xtr, y[f])
            lp = np.full((len(test_texts), len(classes)), np.log(EPS))
            proba = clf.predict_log_proba(Xte)
            for j, c in enumerate(clf.classes_):
                lp[:, classes.index(c)] = proba[:, j]
            out[f] = lp
        return out


class HybridLR(EmbedLR):
    labels: dict = {}

    def fit_predict(self, train_texts, y, test_texts, labels):
        self.labels = labels
        return super().fit_predict(train_texts, y, test_texts, labels)

    """Embeddings + keyword-rule counts (domain vocabulary the small encoder may miss), logistic regression."""

    def __init__(self, repo: str = "BAAI/bge-base-en-v1.5"):
        super().__init__(repo)
        self.name = f"{repo.split('/')[-1]}+rules+LR"

    def _embed(self, texts):
        emb = super()._embed(texts)
        kw = list(theme_patterns(self.labels["theme"]).values()) + list(TYPE_KEYWORDS.values())
        feats = np.array([[min(len(re.findall(p, t.lower())), 3) / 3 for p in kw] for t in texts])
        return np.hstack([emb, feats * 0.5])


class SetFitModel(Base):
    supervised = True

    def __init__(self, repo: str = "BAAI/bge-small-en-v1.5"):
        self.repo = repo
        self.name = f"SetFit({repo.split('/')[-1]})"

    def fit_predict(self, train_texts, y, test_texts, labels):
        from datasets import Dataset
        from setfit import SetFitModel as SFM, Trainer, TrainingArguments

        out = {}
        for f in ("type", "theme"):
            classes = list(labels[f])
            model = SFM.from_pretrained(self.repo, labels=classes)
            ds = Dataset.from_dict({"text": train_texts, "label": [classes.index(v) for v in y[f]]})
            import tempfile

            args = TrainingArguments(output_dir=tempfile.mkdtemp(prefix="setfit-"), batch_size=16, num_epochs=1, num_iterations=10,
                                     show_progress_bar=False, save_strategy="no")
            Trainer(model=model, args=args, train_dataset=ds).train()
            proba = np.asarray(model.predict_proba(test_texts, as_numpy=True))
            full = np.full((len(test_texts), len(classes)), EPS)
            present = sorted(set(classes.index(v) for v in y[f]))
            full[:, present] = proba[:, : len(present)] if proba.shape[1] == len(present) else proba[:, present]
            out[f] = np.log(full + EPS)
        return out


# --------------------------------------------------------------------------- TypeSafe Jev (System One)
class Jev(Base):
    name = "typesafe-jev"
    api = True
    PRICE_PER_M_INPUT = 0.042  # USD, docs.typesafe.ai pricing as of 2026-09

    def available(self):
        try:
            import typesafe_sdk  # noqa: F401
        except ImportError:
            return False, "typesafe-sdk not installed (uv sync --extra typesafe)"
        if not os.environ.get("TYPESAFE_API_KEY"):
            return False, "TYPESAFE_API_KEY not set"
        return True, ""

    def score(self, texts, labels):
        import asyncio

        from typesafe_sdk import AsyncTypeSafeClient, Choice

        async def run():
            out = {f: np.zeros((len(texts), len(labels[f]))) for f in ("type", "theme")}
            tokens = 0
            sem = asyncio.Semaphore(8)
            async with AsyncTypeSafeClient() as client:
                async def one(i, t):
                    nonlocal tokens
                    async with sem:
                        r = await client.system_one(
                            state={"issue": t},
                            questions={
                                "type": Choice(instructions="What kind of GitHub issue is `issue`?", criteria=labels["type"]),
                                "theme": Choice(instructions="Which area of the software project is `issue` mainly about?",
                                                criteria=labels["theme"]),
                            },
                        )
                    for f in ("type", "theme"):
                        probs = r.answers[f].probabilities
                        out[f][i] = [probs.get(c, 0.0) for c in labels[f]]
                    tokens += int(getattr(r.usage, "input_tokens", 0) or 0)
                await asyncio.gather(*(one(i, t) for i, t in enumerate(texts)))
            return out, tokens

        out, tokens = asyncio.run(run())
        self.tokens = tokens
        return {f: np.log(m + EPS) for f, m in out.items()}


def registry() -> dict[str, Base]:
    return {m.name: m for m in [
        Rules(),
        GLiClass("knowledgator/gliclass-edge-v3.0"),
        GLiClass("knowledgator/gliclass-base-v3.0"),
        NLIZeroShot("MoritzLaurer/ModernBERT-base-zeroshot-v2.0"),
        IssueTypeFT(),
        EmbedLR(),
        EmbedLR("BAAI/bge-base-en-v1.5"),
        HybridLR(),
        SetFitModel(),
        Jev(),
    ]}
