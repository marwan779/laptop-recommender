"""Reusable CLI job execution framework for ephemeral Kubernetes CronJob pods.

The base runner owns the cross-cutting lifecycle concerns (argument parsing,
required transaction mode, session creation, commit/rollback, terminal summary,
engine disposal, and OS exit codes) so individual job runners only implement
their domain-specific extension hooks.  This keeps the framework closed for
modification but open for extension via new option fields and CLI flags.
"""

from __future__ import annotations

import argparse
import abc
import asyncio
from dataclasses import dataclass
import logging
import sys
from typing import Any, TextIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, engine as default_engine

logger = logging.getLogger("catalog.jobs.base_cli")


@dataclass
class BaseCliJobOptions:
    """Transaction options shared by every standalone job runner."""

    commit: bool = False
    dry_run: bool = False


class BaseCliJobRunner[OptionsT: BaseCliJobOptions, ResultT](abc.ABC):
    """Template-method CLI runner for one-shot catalog jobs.

    Subclasses extend behaviour through the hooks below without changing the
    base parser, transaction, session, or pod-lifecycle logic:

    * :meth:`register_arguments` - register job-specific CLI flags.
    * :meth:`build_options` - map argparse output to a typed options object.
    * :meth:`execute_job` - perform domain work using the provided session.
    * :meth:`render_summary` - print the terminal report.
    """

    description: str = "Standalone catalog job runner"

    def __init__(
        self,
        *,
        session_factory: Any | None = None,
        engine: Any | None = None,
        stdout: TextIO | None = None,
    ) -> None:
        self._session_factory = session_factory or AsyncSessionLocal
        self._engine = engine or default_engine
        self._stdout = stdout or sys.stdout

    # ─── Extension hooks ────────────────────────────────────────────────────

    def register_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Register job-specific arguments. Override in subclasses."""
        return None

    @abc.abstractmethod
    def build_options(self, parsed_args: argparse.Namespace) -> OptionsT:
        """Map parsed CLI arguments into a strongly typed options object."""

    @abc.abstractmethod
    async def execute_job(self, session: AsyncSession, options: OptionsT) -> ResultT:
        """Execute the one-shot job inside the caller-managed session."""

    def render_summary(self, result: ResultT, options: OptionsT) -> None:
        """Render the terminal report. Override in subclasses as needed."""
        mode = "COMMITTED" if options.commit else "DRY-RUN (rolled back)"
        print(f"Transaction mode: {mode}", file=self._stdout)

    # ─── Template method ────────────────────────────────────────────────────

    def build_parser(self) -> argparse.ArgumentParser:
        """Build the parser, including the mandatory transaction-mode group."""
        parser = argparse.ArgumentParser(description=self.description)
        self.register_arguments(parser)

        transaction_group = parser.add_mutually_exclusive_group(required=True)
        transaction_group.add_argument(
            "--commit",
            action="store_true",
            help="Commit all changes to PostgreSQL after validation.",
        )
        transaction_group.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate all SQL and roll back every change (nothing is persisted).",
        )
        return parser

    async def run(self, argv: list[str] | None = None) -> int:
        """Parse arguments, execute the job, and return a POSIX exit code."""
        args = self.build_parser().parse_args(argv)
        options = self.build_options(args)

        session: AsyncSession | None = None
        try:
            session = self._session_factory()
            result = await self.execute_job(session, options)

            # Flush validates SQL and constraints before any commit/rollback.
            await session.flush()

            if options.commit:
                await session.commit()
            else:
                await session.rollback()

            self.render_summary(result, options)
            return 0
        except SystemExit:
            # argparse already emitted usage and selected the conventional
            # exit code (2 for invalid/missing arguments).
            raise
        except Exception:
            logger.exception("Standalone catalog job failed")
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    logger.exception("Failed to roll back session after job error")
            return 1
        finally:
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    logger.exception("Failed to close database session")
            try:
                await self._engine.dispose()
            except Exception:
                logger.exception("Failed to dispose database engine")

    def run_sync(self, argv: list[str] | None = None) -> int:
        """Synchronous entry point for ``sys.exit(...)`` in CLI scripts."""
        return asyncio.run(self.run(argv))
