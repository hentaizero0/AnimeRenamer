"""Filesystem adapters for triage operations."""

import errno
import os
import shutil
from pathlib import Path

from backend.models import TriageResult


def rename_and_move(source: Path, target: Path, dry_run: bool = False) -> TriageResult:
    if not source.exists() and not dry_run:
        return TriageResult(success=False, source_path=str(source), error_msg=f"Source does not exist: {source}")
    if target.exists() and not dry_run:
        try:
            if source.resolve() == target.resolve():
                return TriageResult(success=True, source_path=str(source), dest_path=str(target))
        except Exception:
            pass
        return TriageResult(success=False, source_path=str(source), dest_path=str(target), error_msg="Target already exists")
    if dry_run:
        return TriageResult(success=True, source_path=str(source), dest_path=str(target))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return TriageResult(success=True, source_path=str(source), dest_path=str(target))
    except Exception as exc:
        return TriageResult(success=False, source_path=str(source), dest_path=str(target), error_msg=str(exc))


def create_hardlink(source: Path, link_target: Path, dry_run: bool = False) -> TriageResult:
    if not source.exists() and not dry_run:
        return TriageResult(success=False, source_path=str(source), dest_path=str(source), error_msg="Source does not exist")
    if link_target.exists() and not dry_run:
        if source.stat().st_ino == link_target.stat().st_ino:
            return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
        return TriageResult(success=False, source_path=str(source), hardlink_path=str(link_target), error_msg="Link target exists and is a different file")
    if dry_run:
        return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
    try:
        link_target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, link_target)
        return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            shutil.copy2(str(source), str(link_target))
            return TriageResult(success=True, source_path=str(source), hardlink_path=str(link_target))
        return TriageResult(success=False, source_path=str(source), hardlink_path=str(link_target), error_msg=str(exc))


def rollback_moves(moves: list[tuple[Path, Path]]) -> None:
    for source, target in reversed(moves):
        try:
            shutil.move(str(target), str(source))
        except Exception:
            continue
