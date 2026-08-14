"""Populate stored runbook embeddings as an explicit corpus setup command."""

import argparse

from resolve_ai.retrieval import populate_runbook_embeddings


def main() -> None:
    """Parse the database URL and embed runbooks that currently need vectors."""
    parser = argparse.ArgumentParser(
        description="Populate missing semantic runbook embeddings."
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="PostgreSQL connection URL containing the runbook corpus.",
    )
    args = parser.parse_args()

    populated = populate_runbook_embeddings(args.database_url)
    print(f"Populated runbook embeddings: {populated}")


if __name__ == "__main__":
    main()
