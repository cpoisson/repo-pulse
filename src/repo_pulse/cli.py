from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import config as config_mod


def _as_of(args) -> str:
    return args.as_of or dt.date.today().isoformat()


def cmd_issues(cfg, args):
    """Compact issue list (number, labels, title + body snippet) to read when proposing themes or pre-labelling."""
    from .classify import issue_text
    from .collect.cache import load_all

    for i in load_all(cfg.slug, _as_of(args))["issues"]:
        print(f"#{i['number']} [{','.join(i['labels'])}] {issue_text(i, args.chars)}")


def cmd_digest(cfg, args):
    """The compact metrics digest the narrative is written from (same text the LLM call would see)."""
    from .llm.narrate import digest

    print(digest(json.loads((Path("data") / cfg.slug / f"metrics-{_as_of(args)}.json").read_text())))


def cmd_collect(cfg, args):
    from . import collect

    collect.run(cfg, _as_of(args), refresh=args.refresh)


def cmd_analyze(cfg, args):
    from .collect.cache import load_all
    from .metrics import compute

    raw = load_all(cfg.slug, _as_of(args))
    metrics = compute(cfg, raw, _as_of(args))
    out = Path("data") / cfg.slug / f"metrics-{_as_of(args)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=1, default=str))
    print(f"wrote {out}", file=sys.stderr)
    return metrics


def cmd_classify(cfg, args):
    from .classify.run import classify_corpus

    classify_corpus(cfg, _as_of(args), model=args.model, mode=args.classifier)


def cmd_narrate(cfg, args):
    from .llm.narrate import narrate

    narrate(cfg, _as_of(args), use_llm=not args.no_llm)


def cmd_build(cfg, args):
    from .deck.build import build

    path = build(cfg, _as_of(args), anonymize=getattr(args, "anonymize", False), note=getattr(args, "note", None),
                 out=getattr(args, "out", None))
    print(path)


def cmd_all(cfg, args):
    cmd_collect(cfg, args)
    cmd_classify(cfg, args)
    cmd_analyze(cfg, args)
    cmd_narrate(cfg, args)
    cmd_build(cfg, args)


def cmd_gold(cfg, args):
    from .classify import gold

    if args.prelabels:
        gold.import_prelabels(cfg, args.prelabels, args.source)
    if args.import_reviewed:
        gold.import_reviewed(cfg, args.import_reviewed)
    print(gold.status(gold.load(cfg)), file=sys.stderr)
    print(gold.make_review_page(cfg, _as_of(args)))


def cmd_bakeoff(cfg, args):
    from .classify.bakeoff import run_bakeoff

    print(run_bakeoff(cfg, _as_of(args), models=args.models.split(",") if args.models else None, mode=args.classifier))


def _load_dotenv(path: Path = Path(".env")) -> None:
    """KEY=value lines from a gitignored .env (API keys stay out of shell history and chat)."""
    import os

    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main(argv=None):
    _load_dotenv()
    p = argparse.ArgumentParser(prog="repo-pulse")
    p.add_argument("--config", "-c", help="config file, e.g. configs/<name>.yaml (create one with `repo-pulse init owner/name`)")
    p.add_argument("--as-of", help="edition date YYYY-MM-DD (default today)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect"); c.add_argument("--refresh", action="store_true")
    sub.add_parser("analyze")
    modes = ("local", "auto", "jev")
    c = sub.add_parser("classify"); c.add_argument("--model", default=None, help="override config/selected model")
    c.add_argument("--classifier", choices=modes, default=None, help="override config `classifier` (default local = free)")
    c = sub.add_parser("narrate"); c.add_argument("--no-llm", action="store_true")
    b = sub.add_parser("build")
    b.add_argument("--anonymize", action="store_true", help="show roles (maintainer A, contributor 1) instead of people's names")
    b.add_argument("--note", help="extra line on the title slide, e.g. a snapshot disclaimer")
    b.add_argument("--out", help="output path (default out/<name>-pulse-<as_of>.html)")
    c = sub.add_parser("all"); c.add_argument("--refresh", action="store_true"); c.add_argument("--no-llm", action="store_true"); c.add_argument("--model", default=None)
    c.add_argument("--classifier", choices=modes, default=None)
    c = sub.add_parser("gold", help="manage the gold label set + write the review page")
    c.add_argument("--prelabels", help="file of '<number> <type> <theme>' lines"); c.add_argument("--source", default="llm-prelabel", help="who pre-labelled, e.g. the agent/model name")
    c.add_argument("--import", dest="import_reviewed", help="reviewed.json exported from the review page")
    c = sub.add_parser("bakeoff", help="compare classifiers on the gold set"); c.add_argument("--models", default=None)
    c.add_argument("--classifier", choices=modes, default=None, help="override config `classifier` (local skips API models)")
    c = sub.add_parser("init", help="clone a public repo and write a starter config"); c.add_argument("repo", help="owner/name, or a github.com / gitlab.com URL")
    c.add_argument("--window", type=int, default=90)
    sub.add_parser("digest", help="print the compact metrics digest used to write the narrative")
    c = sub.add_parser("issues", help="print a compact issue list (for taxonomy / labelling)"); c.add_argument("--chars", type=int, default=300)
    args = p.parse_args(argv)
    if args.cmd == "init":
        from .init import init

        print(init(args.repo, window_days=args.window))
        return
    if not args.config:
        p.error("--config is required (create one with `repo-pulse init owner/name`)")
    cfg = config_mod.load(args.config)
    globals()[f"cmd_{args.cmd}"](cfg, args)


if __name__ == "__main__":
    main()
