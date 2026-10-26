"""Pydantic v2 schemas: parsed DICOM-RT payloads and API response models.

Missing DICOM attributes are represented as ``None``; they are never invented.
Every parsed section carries its own ``warnings`` array so the API consumer
can see exactly which fields were absent.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- Parsed domain payloads --------------------------------------------------
class PlanBeam(BaseModel):
    beam_number: int | None = None
    beam_name: str | None = None
    treatment_machine_name: str | None = None
    radiation_type: str | None = None
    beam_type: str | None = None
    treatment_delivery_type: str | None = None
    nominal_beam_energy: float | None = Field(default=None, description="Nominal beam energy (MV for photons).")
    gantry_angle: float | None = Field(default=None, description="Gantry angle in degrees.")
    collimator_angle: float | None = Field(default=None, description="Collimator angle in degrees.")
    couch_angle: float | None = Field(default=None, description="Couch (patient support) angle in degrees.")
    referenced_beam_number: int | None = Field(
        default=None,
        description="Dose-reference linkage from FractionGroupSequence.ReferencedBeamSequence.",
    )
    beam_dose: float | None = Field(default=None, description="Beam dose (Gy) per fraction, when referenced.")
    beam_meterset: float | None = Field(default=None, description="Beam meterset (MU), when referenced.")


class PlanInfo(BaseModel):
    plan_label: str | None = None
    plan_name: str | None = None
    plan_date: str | None = None
    approval_status: str | None = None
    number_of_fractions: int | None = None
    number_of_beams: int | None = None
    prescription_dose: float | None = None
    referenced_structure_set_sop_uid: str | None = None
    beams: list[PlanBeam] = Field(default_factory=list)
    parser: str = "pydicom"
    warnings: list[str] = Field(default_factory=list)


class RoiSummary(BaseModel):
    roi_number: int
    roi_name: str | None = None
    roi_type: str | None = None
    contour_count: int | None = None


class StructureInfo(BaseModel):
    structure_set_label: str | None = None
    structure_set_date: str | None = None
    rois: list[RoiSummary] = Field(default_factory=list)
    roi_count: int = 0
    parser: str = "pydicom"
    warnings: list[str] = Field(default_factory=list)


class DoseGridInfo(BaseModel):
    rows: int | None = None
    columns: int | None = None
    number_of_frames: int | None = None
    pixel_spacing: list[float] | None = None
    image_position_patient: list[float] | None = None
    dose_grid_scaling: float | None = None
    grid_frame_offset_count: int | None = None


class DvhSeries(BaseModel):
    roi_number: int | None = None
    roi_name: str | None = None
    dvh_type: str | None = None
    dose_units: str | None = None
    dose_type: str | None = None
    volume_units: str | None = None
    number_of_bins: int | None = None
    dose_bins: list[float] | None = None
    volumes: list[float] | None = None
    initial_volume: float | None = None
    min_dose: float | None = None
    max_dose: float | None = None
    mean_dose: float | None = None


class DoseInfo(BaseModel):
    dose_units: str | None = None
    dose_type: str | None = None
    dose_summation_type: str | None = None
    grid: DoseGridInfo | None = None
    has_dvh: bool = False
    dvh: list[DvhSeries] = Field(default_factory=list)
    parser: str = "pydicom"
    warnings: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """The parsed payload stored on the analysis record and returned by the API."""

    rt_object_type: str
    source: str
    structures: StructureInfo | None = None
    plan: PlanInfo | None = None
    dose: DoseInfo | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# --- API response models -------------------------------------------------------
class HistoryItem(BaseModel):
    analysis_id: str
    created_at: str | None = None
    rt_object_type: str
    status: str
    source: str
    warning_count: int = 0
    error_count: int = 0
    trace_id: str | None = None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AuditEventOut(BaseModel):
    id: int
    created_at: str | None = None
    analysis_id: str
    event_type: str
    detail: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class AnalysisDetail(BaseModel):
    analysis_id: str
    created_at: str | None = None
    rt_object_type: str
    status: str
    source: str
    trace_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    audit_events: list[AuditEventOut] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    database: bool
    environment: str
    version: str
    time: str
