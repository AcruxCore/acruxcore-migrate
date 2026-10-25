"""Command line: `acruxcore-migrate <source> [options]`. One subcommand per source platform."""
import argparse
import asyncio
import os
import sys

from . import __version__
from .langfuse import LangfuseSource, migrate_all


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="acruxcore-migrate",
        description="Move prompts into AcruxCore. Reads ACRUXCORE_API_KEY and ACRUXCORE_BASE_URL.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sources = parser.add_subparsers(dest="source", required=True)

    lf = sources.add_parser(
        "langfuse",
        help="copy prompts from a Langfuse project",
        description="Copy prompts from a Langfuse project. Reads LANGFUSE_PUBLIC_KEY, "
        "LANGFUSE_SECRET_KEY and LANGFUSE_HOST (default https://cloud.langfuse.com).",
    )
    lf.add_argument("names", nargs="*", help="prompt names to migrate (default: all)")
    lf.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    lf.add_argument("--text-role", default="user", choices=["system", "user"],
                    help="role for the one message a Langfuse text prompt becomes (default: user)")

    args = parser.parse_args(argv)

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        sys.exit("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    with LangfuseSource(host, public_key, secret_key) as source:
        asyncio.run(migrate_all(source, args.names, args.text_role, args.dry_run))
