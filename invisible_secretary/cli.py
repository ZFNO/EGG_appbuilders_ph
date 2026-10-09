import os
import sys

# Allow `python cli.py` from inside this folder (project root must be importable).
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invisible_secretary import Engine
from invisible_secretary.factory import default_adapter
from invisible_secretary.model_registry import discover_models, resolve_model


def _fmt_size(mb: float) -> str:
    return f"{mb/1024:.2f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def print_models(models: list[dict], selected: str | None = None) -> None:
    if not models:
        print("No local models found under ./models (or legacy bundle paths).")
        return
    print(f"Local models ({len(models)}):\n")
    print(f"  {'#':>2}  {'MODEL':<26} {'QUANT':<6} {'SIZE':>9}  {'SOURCE':<9}  PATH")
    for i, m in enumerate(models, 1):
        mark = " *" if selected and selected == m["path"] else "  "
        print(f"  {i:>2}{mark} {m['name']:<26} {m['quant']:<6} "
              f"{_fmt_size(m['size_mb']):>9}  {m['source']:<9}  {m['path']}")
    print("\n  * = currently selected\n")


def choose_model(interactive: bool = True) -> str | None:
    """Interactive model picker. Returns a model id/path (or None to skip)."""
    models = discover_models()
    if not models:
        print("No local models found; running with rules only.")
        return None
    print_models(models, selected=models[0]["path"])
    if not interactive:
        return models[0]["id"]
    while True:
        raw = input(f"Select model [1-{len(models)}], Enter for #1, 'n' for none: ").strip().lower()
        if raw == "":
            return models[0]["id"]
        if raw in ("n", "none", "q", "quit"):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            return models[int(raw) - 1]["id"]
        print("  invalid choice, try again.")


def _run_demo(eng: Engine, adapter_name: str) -> None:
    print(f"== Invisible Secretary :: demo  (adapter={adapter_name}) ==\n")

    print("1) Owner: 'Ask the supplier to confirm today's delivery'")
    ev = eng.process("req_demo_001", "Ask the supplier to confirm today's delivery")
    print(f"   intent={ev.decision.intent.value} node={ev.decision.node.value} "
          f"state={ev.state} risk={ev.decision.risk_level.value}")
    print(f"   draft -> {ev.result.summary}")
    appr = ev.pending_approval
    print(f"   approval card: {appr['description']}  (target={appr['target']})\n")

    print("2) Owner approves the exact pending action")
    ev = eng.approve(appr["approval_id"], payload=appr["payload"])
    print(f"   state={ev.state} :: {ev.result.summary}\n")

    print("3) Owner: 'Handle the issue with the order' (ambiguous)")
    ev = eng.process("req_demo_002", "Handle the issue with the order")
    print(f"   state={ev.state} :: {ev.result.summary}\n")

    print("4) Owner: 'Pay the supplier their deposit now, urgently'")
    ev = eng.process("req_demo_003", "Pay the supplier their deposit now, urgently")
    print(f"   intent={ev.decision.intent.value} state={ev.state} "
          f"(high urgency did NOT grant authorization)\n")

    print("5) Nodes available:")
    for name, node in eng.nodes.items():
        print(f"   - {node.health()}")
    print("\n== end demo ==")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="invisible_secretary.cli",
                                 description="Invisible Secretary demo / model picker")
    ap.add_argument("--list-models", action="store_true", help="list local models and exit")
    ap.add_argument("--pick", action="store_true", help="interactively pick a model")
    ap.add_argument("--model", default=None, help="model id, folder name, or path")
    ap.add_argument("--no-model", action="store_true", help="rules only, load no model")
    args = ap.parse_args(argv)

    if args.list_models:
        print_models(discover_models())
        return 0

    use_model = not args.no_model
    model = None
    if use_model:
        if args.pick:
            model = choose_model(interactive=True)
            use_model = model is not None
        elif args.model:
            model = args.model
            if resolve_model(model) is None:
                print(f"model '{model}' not found; try --list-models", file=sys.stderr)
                return 2
            print(f"Using model: {model}")

    adapter = default_adapter(use_model=use_model, model=model)
    engine = Engine(adapter)
    _run_demo(engine, adapter.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
