"""Smoke import tests (no DB required for module load if env is set)."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") or not os.environ.get("SECRET_KEY"),
    reason="Set DATABASE_URL and SECRET_KEY to run smoke imports",
)


def test_import_app():
    import app.main as main  # noqa: F401

    assert main.app.title


def test_import_celery():
    from app.tasks.celery_app import celery_app

    assert celery_app.main
