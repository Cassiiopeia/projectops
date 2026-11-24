"""Destination adapters by kind. Add an engine: write adapters/<engine>.py with an Adapter subclass, register it here."""
from __future__ import annotations

from .base import Adapter, UnsupportedAdapter
from .gbrain_local import GbrainLocalAdapter
from .gbrain_remote import GbrainRemoteAdapter
from .repo_files import RepoFilesAdapter

ADAPTERS = {adapter.kind: adapter for adapter in (RepoFilesAdapter, GbrainLocalAdapter, GbrainRemoteAdapter)}


def adapter_for(destination: dict, context: dict) -> Adapter:
    """Destination kind > adapter instance; an unknown kind gets UnsupportedAdapter (clear code, never a crash)"""
    return ADAPTERS.get(destination.get("kind"), UnsupportedAdapter)(destination, context)
