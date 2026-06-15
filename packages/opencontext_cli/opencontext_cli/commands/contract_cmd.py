"""Context contract CLI commands."""

from __future__ import annotations

import argparse
import sys


def add_contract_commands(subparsers: argparse._SubParsersAction) -> None:
    contract = subparsers.add_parser("contract", help="Context contract operations")
    sub = contract.add_subparsers(dest="contract_cmd", help="contract subcommands")

    build = sub.add_parser("build", help="Build a verified context contract for a query")
    build.add_argument("--query", "-q", required=True, help="Task description")
    build.add_argument("--output", choices=["yaml", "json"], default="yaml")
    build.add_argument("--root", default=".", help="Project root")


def handle_contract(args: argparse.Namespace, config=None) -> int:
    cmd = getattr(args, "contract_cmd", None)
    if cmd == "build":
        return _handle_contract_build(args, config)
    print("Usage: opencontext contract build --query <task>", file=sys.stderr)
    return 1


def _handle_contract_build(args: argparse.Namespace, config=None) -> int:
    try:
        from opencontext_core.context.planning.classifier import TaskClassifier
        from opencontext_core.context.planning.contract import ContextContractBuilder
        from opencontext_core.context.planning.risk import RiskClassifier

        contract = ContextContractBuilder(
            classifier=TaskClassifier(),
            risk_classifier=RiskClassifier(),
        ).build(args.query)

        if args.output == "json":
            import json

            print(json.dumps(contract.model_dump(), indent=2, default=str))
        else:
            print(contract.to_yaml())
        return 0
    except Exception as e:
        print(f"Error building contract: {e}", file=sys.stderr)
        return 1
