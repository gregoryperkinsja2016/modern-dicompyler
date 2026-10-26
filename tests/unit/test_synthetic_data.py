"""Unit tests for the deterministic synthetic demo data."""
from __future__ import annotations

from pydicom import dcmread

from src.synthetic_data import (
    BEAM_DOSE_GY,
    DVH_NUMBER_OF_BINS,
    PLAN_NUMBER_OF_BEAMS,
    PLAN_NUMBER_OF_FRACTIONS,
    PRESCRIPTION_DOSE_GY,
    ROI_DEFINITIONS,
    build_synthetic_datasets,
    build_synthetic_rtdose,
    build_synthetic_rtplan,
    build_synthetic_rtstruct,
    dataset_to_bytes,
)


def test_dataset_build_is_deterministic():
    first_plan, first_struct, first_dose = build_synthetic_datasets()
    second_plan, second_struct, second_dose = build_synthetic_datasets()
    assert str(first_plan) == str(second_plan)
    assert str(first_struct) == str(second_struct)
    assert str(first_dose) == str(second_dose)


def test_uids_are_stable_across_builds():
    first_plan, _, first_dose = build_synthetic_datasets()
    second_plan, _, second_dose = build_synthetic_datasets()
    assert first_plan.SOPInstanceUID == second_plan.SOPInstanceUID
    assert first_dose.SOPInstanceUID == second_dose.SOPInstanceUID


def test_plan_constants_are_internally_consistent():
    total_dose = BEAM_DOSE_GY * PLAN_NUMBER_OF_BEAMS * PLAN_NUMBER_OF_FRACTIONS
    assert total_dose == PRESCRIPTION_DOSE_GY


def test_plan_dataset_matches_constants():
    dataset = build_synthetic_rtplan()
    assert str(dataset.RTPlanLabel) == "SYNTH-PLAN-01"
    assert len(dataset.BeamSequence) == PLAN_NUMBER_OF_BEAMS
    assert int(dataset.BeamSequence[0].BeamNumber) == 1
    assert len(dataset.BeamSequence[0].ControlPointSequence) == 1


def test_struct_dataset_matches_definitions():
    dataset = build_synthetic_rtstruct()
    names = [str(roi.ROIName) for roi in dataset.StructureSetROISequence]
    assert names == [definition[1] for definition in ROI_DEFINITIONS]
    contour_counts = [len(item.ContourSequence) for item in dataset.ROIContourSequence]
    assert contour_counts == [definition[4] for definition in ROI_DEFINITIONS]


def test_dose_dataset_grid_and_dvh_shape():
    dataset = build_synthetic_rtdose()
    assert int(dataset.Rows) == 16
    assert int(dataset.Columns) == 16
    assert len(dataset.DVHSequence) == 1
    dvh_item = dataset.DVHSequence[0]
    assert len(dvh_item.DVHData) == 2 * DVH_NUMBER_OF_BINS
    assert int(dvh_item.DVHReferencedROISequence[0].ReferencedROINumber) == 2


def test_dataset_to_bytes_roundtrip():
    from io import BytesIO

    original = build_synthetic_rtplan()
    parsed = dcmread(BytesIO(dataset_to_bytes(original)), force=True, stop_before_pixels=True)
    assert str(parsed.Modality) == "RTPLAN"
    assert str(parsed.RTPlanLabel) == str(original.RTPlanLabel)
