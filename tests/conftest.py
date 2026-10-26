"""Shared pytest fixtures for Modern Dicompyler tests.

The temporary SQLite database URL is configured before any ``src`` module that
reads configuration is imported (``src.main``/``src.db`` are imported lazily
inside the ``client`` fixture, after the environment variable is set).
"""
from __future__ import annotations

import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="dicomrt-tests-")
os.environ["RTQA_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMPDIR, 'test.db')}"

import pytest
from fastapi.testclient import TestClient
from pydicom.dataset import Dataset
from pydicom.uid import CTImageStorage, generate_uid

from src.synthetic_data import build_synthetic_rtplan, dataset_to_bytes


@pytest.fixture(scope="session")
def client():
    from src import db

    db.init_db()
    from src.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def rtplan_bytes() -> bytes:
    return dataset_to_bytes(build_synthetic_rtplan())


@pytest.fixture()
def ct_bytes() -> bytes:
    """A minimal, valid, but *unsupported* (non-RT) DICOM object."""
    dataset = Dataset()
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = generate_uid(entropy_srcs=["modern-dicompyler-test", "ct"])
    dataset.Modality = "CT"
    dataset.PatientID = "TEST-CT"
    dataset.StudyInstanceUID = generate_uid(entropy_srcs=["modern-dicompyler-test", "ct-study"])
    dataset.SeriesInstanceUID = generate_uid(entropy_srcs=["modern-dicompyler-test", "ct-series"])
    return dataset_to_bytes(dataset)
