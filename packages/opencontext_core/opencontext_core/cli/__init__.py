"""CLI library — ``opencontext benchmark release`` verdict command.

The library surface for the release verdict command. Lives in
``opencontext_core`` so the contract is testable without the CLI
package; the actual argparse wiring in
``opencontext_cli.commands.benchmark_cmd`` is a thin wrapper that
calls :func:`main` here.

The command runs the 12 release gates (commit 015) and the 12 §A
suites (commit 016), prints the verdict, and exits 0 iff the verdict
is ``1.0_READY``.
"""
