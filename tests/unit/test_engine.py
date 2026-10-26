"""Unit tests for the DICOM-RT parsing engine (typed errors, nulls, warnings)."""
from __future__ import annotations

import pytest
from pydicom.dataset import Dataset

from src.engine import (
    DatabaseUnavailableError,
    InvalidDICOMError,
    MissingRequiredAttributeError,
    RTQAError,
    UnsupportedRTObjectError,
    detect_rt_object,
    parse_dataset_bytes,
    parse_rtdose,
    parse_rtplan,
    parse_rtstruct,
    run_synthetic_demo_case,
)
from src.synthetic_data import (
    build_synthetic_datasets,
    build_synthetic_rtdose,
    build_synthetic_rtplan,
    build_synthetic_rtstruct,
)


# ---------------------------------------------------------------------------
# Synthetic demo case
# ---------------------------------------------------------------------------
def test_demo_case_is_deterministic():
    first = run_synthetic_demo_case()
    second = run_synthetic_demo_case()
    assert first.model_dump() == second.model_dump()
    assert first.rt_object_type == "DEMO_CASE"
    assert first.source == "demo_case"
    assert first.plan is not None
    assert first.structures is not None
    assert first.dose is not None
    assert first.errors == []


def test_demo_case_dvh_links_to_struct_roi_name():
    result = run_synthetic_demo_case()
    assert result.dose is not None
    assert result.dose.dvh[0].roi_name == "SYNTH_PTV"


# ---------------------------------------------------------------------------
# detect_rt_object
# ---------------------------------------------------------------------------
def test_detect_rt_object_for_all_supported_types():
    plan, structure, dose = build_synthetic_datasets()
    assert detect_rt_object(plan) == "RTPLAN"
    assert detect_rt_object(structure) == "RTSTRUCT"
    assert detect_rt_object(dose) == "RTDOSE"


def test_detect_rt_object_rejects_dataset_without_modality():
    with pytest.raises(InvalidDICOMError):
        detect_rt_object(Dataset())


# ---------------------------------------------------------------------------
# RTPLAN parsing
# ---------------------------------------------------------------------------
def test_parse_rtplan_beam_metadata():
    plan = parse_rtplan(build_synthetic_rtplan())
    assert plan.plan_label == "SYNTH-PLAN-01"
    assert plan.plan_name == "Synthetic Two-Field Plan"
    assert plan.approval_status == "UNAPPROVED"
    assert plan.number_of_fractions == 30
    assert plan.number_of_beams == 2
    assert plan.prescription_dose == 60.0
    assert plan.referenced_structure_set_sop_uid
    assert len(plan.beams) == 2

    beam_one = plan.beams[0]
    assert beam_one.beam_name == "SYNTH-BEAM-01"
    assert beam_one.treatment_machine_name == "SYNTH-LINAC-01"
    assert beam_one.radiation_type == "PHOTON"
    assert beam_one.beam_type == "STATIC"
    assert beam_one.treatment_delivery_type == "TREATMENT"
    assert beam_one.nominal_beam_energy == 6.0
    assert beam_one.gantry_angle == 0.0
    assert beam_one.collimator_angle == 0.0
    assert beam_one.couch_angle == 0.0
    assert beam_one.referenced_beam_number == 1
    assert beam_one.beam_dose == 1.0
    assert beam_one.beam_meterset == 100.0
    assert plan.beams[1].gantry_angle == 90.0
    assert plan.beams[1].beam_meterset == 120.0


def test_missing_plan_fields_become_null_with_warnings():
    dataset = build_synthetic_rtplan()
    del dataset.RTPlanName
    del dataset.BeamSequence[0].ControlPointSequence[0].GantryAngle
    del dataset.FractionGroupSequence

    plan = parse_rtplan(dataset)
    assert plan.plan_name is None
    assert plan.beams[0].gantry_angle is None
    assert plan.number_of_fractions is None
    beam_one = plan.beams[0]
    assert beam_one.referenced_beam_number is None
    assert beam_one.beam_dose is None
    assert beam_one.beam_meterset is None

    joined = " | ".join(plan.warnings)
    assert "RTPlanName" in joined
    assert "GantryAngle" in joined
    assert "FractionGroupSequence" in joined


def test_rtplan_without_beam_sequence_raises_typed_error():
    dataset = build_synthetic_rtplan()
    del dataset.BeamSequence
    with pytest.raises(MissingRequiredAttributeError):
        parse_rtplan(dataset)


# ---------------------------------------------------------------------------
# RTSTRUCT parsing
# ---------------------------------------------------------------------------
def test_parse_rtstruct_rois():
    structures = parse_rtstruct(build_synthetic_rtstruct())
    assert structures.roi_count == 3
    assert structures.structure_set_label == "SYNTH-STRUCT-01"
    by_number = {roi.roi_number: roi for roi in structures.rois}
    assert by_number[1].roi_name == "SYNTH_BODY"
    assert by_number[1].roi_type == "EXTERNAL"
    assert by_number[2].roi_name == "SYNTH_PTV"
    assert by_number[2].roi_type == "PTV"
    assert by_number[2].contour_count == 6
    assert by_number[3].contour_count == 3


def test_rtstruct_without_roi_sequence_raises_typed_error():
    dataset = build_synthetic_rtstruct()
    del dataset.StructureSetROISequence
    with pytest.raises(MissingRequiredAttributeError):
        parse_rtstruct(dataset)


def test_missing_struct_fields_become_null_with_warnings():
    dataset = build_synthetic_rtstruct()
    del dataset.ROIContourSequence
    del dataset.StructureSetROISequence[0].ROIName

    structures = parse_rtstruct(dataset)
    assert structures.rois[0].roi_name is None
    assert structures.rois[0].contour_count is None
    joined = " | ".join(structures.warnings)
    assert "ROIContourSequence" in joined
    assert "ROIName" in joined


# ---------------------------------------------------------------------------
# RTDOSE parsing
# ---------------------------------------------------------------------------
def test_parse_rtdose_grid_and_dvh():
    dose = parse_rtdose(build_synthetic_rtdose())
    assert dose.dose_units == "GY"
    assert dose.dose_summation_type == "PLAN"
    assert dose.grid.rows == 16
    assert dose.grid.columns == 16
    assert dose.grid.number_of_frames == 4
    assert dose.grid.dose_grid_scaling == 1e-6
    assert dose.has_dvh is True
    series = dose.dvh[0]
    assert series.roi_number == 2
    assert series.number_of_bins == 20
    assert series.dose_bins is not None and len(series.dose_bins) == 20
    assert series.volumes is not None and len(series.volumes) == 20
    assert series.volumes[0] == 100.0
    assert series.max_dose is not None
    assert series.mean_dose is not None


def test_rtdose_without_dvh_sequence_warns_and_degrades():
    dataset = build_synthetic_rtdose()
    del dataset.DVHSequence
    dose = parse_rtdose(dataset)
    assert dose.has_dvh is False
    assert dose.dvh == []
    assert any("DVHSequence" in warning for warning in dose.warnings)


def test_rtdose_missing_grid_fields_become_null_with_warnings():
    dataset = build_synthetic_rtdose()
    del dataset.PixelSpacing
    dose = parse_rtdose(dataset)
    assert dose.grid.pixel_spacing is None
    assert any("PixelSpacing" in warning for warning in dose.warnings)


# ---------------------------------------------------------------------------
# Byte-level parsing and typed error behaviour
# ---------------------------------------------------------------------------
def test_malformed_bytes_raise_invalid_dicom_error():
    with pytest.raises(InvalidDICOMError):
        parse_dataset_bytes(b"this is definitely not a dicom file")


def test_empty_bytes_raise_invalid_dicom_error():
    with pytest.raises(InvalidDICOMError):
        parse_dataset_bytes(b"")


def test_unsupported_rt_object_raises_typed_error(ct_bytes):
    with pytest.raises(UnsupportedRTObjectError) as excinfo:
        parse_dataset_bytes(ct_bytes)
    assert excinfo.value.error_class == "UnsupportedRTObjectError"


def test_error_taxonomy_hierarchy():
    assert issubclass(InvalidDICOMError, RTQAError)
    assert issubclass(UnsupportedRTObjectError, RTQAError)
    assert issubclass(MissingRequiredAttributeError, RTQAError)
    assert issubclass(DatabaseUnavailableError, RTQAError)
    assert issubclass(RTQAError, Exception)


def test_parse_dataset_bytes_rtplan_roundtrip(rtplan_bytes):
    rt_object_type, result = parse_dataset_bytes(rtplan_bytes)
    assert rt_object_type == "RTPLAN"
    assert result.source == "upload"
    assert result.plan is not None
    assert result.plan.plan_label == "SYNTH-PLAN-01"
    assert result.structures is None
    assert result.dose is None
    assert result.errors == []
