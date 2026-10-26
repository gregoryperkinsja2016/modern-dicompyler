"""Domain engine: RT object detection, parsing, and the synthetic demo case.

Design rules implemented here:

- Missing DICOM attributes become ``None`` **and** are appended to a warnings
  array. Values are never invented.
- Structural omissions (e.g. an RTSTRUCT without ``StructureSetROISequence``)
  raise typed exceptions from the error taxonomy.
- ``dicompyler-core`` is used only where compatible (DVH statistics from the
  RTDOSE ``DVHSequence`` and RTSTRUCT type enrichment) with graceful
  degradation to pure pydicom parsing if it is unavailable or fails.
- Nothing in this module logs DICOM contents or PHI.
"""
from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from pydicom import Dataset, dcmread
from pydicom.errors import InvalidDicomError

from src.schemas import (
    AnalysisResult,
    DoseGridInfo,
    DoseInfo,
    DvhSeries,
    PlanBeam,
    PlanInfo,
    RoiSummary,
    StructureInfo,
)
from src.synthetic_data import build_synthetic_datasets


# ---------------------------------------------------------------------------
# Typed error taxonomy
# ---------------------------------------------------------------------------
class RTQAError(Exception):
    """Base class for all Modern Dicompyler domain errors."""

    error_class = "RTQAError"


class InvalidDICOMError(RTQAError):
    """The uploaded data is not a usable DICOM file/dataset."""

    error_class = "InvalidDICOMError"


class UnsupportedRTObjectError(RTQAError):
    """The DICOM object is valid but is not a supported RT object."""

    error_class = "UnsupportedRTObjectError"


class MissingRequiredAttributeError(RTQAError):
    """A structurally required DICOM attribute/sequence is absent."""

    error_class = "MissingRequiredAttributeError"


class DatabaseUnavailableError(RTQAError):
    """The persistence layer could not be reached or written to."""

    error_class = "DatabaseUnavailableError"


# ---------------------------------------------------------------------------
# Optional dicompyler-core integration (graceful degradation)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import success/failure depends on the environment
    from dicompylercore import dicomparser
    from dicompylercore import dvh as dvh_module

    DICOMPYLER_AVAILABLE = True
    _DICOMPYLER_IMPORT_ERROR = ""
except Exception as exc:  # noqa: BLE001 - any import failure must degrade safely
    DICOMPYLER_AVAILABLE = False
    _DICOMPYLER_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


RT_OBJECT_TYPES = ("RTPLAN", "RTSTRUCT", "RTDOSE")
_SOP_CLASS_TO_RT_TYPE = {
    "1.2.840.10008.5.1.4.1.1.481.5": "RTPLAN",
    "1.2.840.10008.5.1.4.1.1.481.3": "RTSTRUCT",
    "1.2.840.10008.5.1.4.1.1.481.2": "RTDOSE",
}
_DVH_MAX_BIN_COUNT = 400


# ---------------------------------------------------------------------------
# Small warning-aware attribute helpers
# ---------------------------------------------------------------------------
def _missing_warning(attribute: str, context: str) -> str:
    return f"{context}: attribute '{attribute}' is missing; value set to null."


def _get_attribute(dataset: Dataset, attribute: str, context: str, warnings: list[str]) -> Any:
    if attribute in dataset:
        return dataset[attribute].value
    warnings.append(_missing_warning(attribute, context))
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _nan_to_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(numeric) else numeric


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def detect_rt_object(dataset: Dataset) -> str:
    """Return ``RTPLAN``/``RTSTRUCT``/``RTDOSE`` for a supported DICOM-RT object.

    Raises ``UnsupportedRTObjectError`` for valid-but-unsupported modalities
    and ``InvalidDICOMError`` when the dataset cannot be identified at all.
    """
    modality = getattr(dataset, "Modality", None)
    if modality:
        normalized = str(modality).upper().strip()
        if normalized in RT_OBJECT_TYPES:
            return normalized
        raise UnsupportedRTObjectError(
            f"Detected unsupported DICOM object with Modality '{normalized}'. "
            f"Supported types: {', '.join(RT_OBJECT_TYPES)}."
        )
    sop_class_uid = str(getattr(dataset, "SOPClassUID", "") or "")
    if sop_class_uid in _SOP_CLASS_TO_RT_TYPE:
        return _SOP_CLASS_TO_RT_TYPE[sop_class_uid]
    raise InvalidDICOMError(
        "Dataset has neither a supported RT Modality nor a recognised RT SOP Class UID; "
        "not a usable DICOM-RT object."
    )


# ---------------------------------------------------------------------------
# RTPLAN parsing
# ---------------------------------------------------------------------------
def _parse_plan_beam(
    beam_item: Dataset, dose_references: dict[int, dict[str, Any]], warnings: list[str]
) -> PlanBeam:
    beam_number = _as_int(beam_item.get("BeamNumber"))
    context = f"RTPLAN beam {beam_number if beam_number is not None else '?'}"
    if beam_number is None:
        warnings.append(f"{context}: 'BeamNumber' is missing; value set to null.")

    control_point = None
    if "ControlPointSequence" in beam_item and len(beam_item.ControlPointSequence) > 0:
        control_point = beam_item.ControlPointSequence[0]
    else:
        warnings.append(
            f"{context}: 'ControlPointSequence' is missing; control-point level attributes set to null."
        )

    def get(name: str, source: Dataset | None) -> Any:
        if source is not None:
            return _get_attribute(source, name, context, warnings)
        warnings.append(_missing_warning(name, context))
        return None

    energy = _as_float(get("NominalBeamEnergy", control_point))
    gantry = _as_float(get("GantryAngle", control_point))
    collimator = _as_float(get("BeamLimitingDeviceAngle", control_point))
    couch = _as_float(get("PatientSupportAngle", control_point))

    reference = dose_references.get(beam_number) if beam_number is not None else None
    if reference is None and beam_number is not None:
        warnings.append(
            f"{context}: not referenced by FractionGroupSequence; "
            "dose-reference linkage (beam dose/meterset) set to null."
        )

    return PlanBeam(
        beam_number=beam_number,
        beam_name=str(value) if (value := beam_item.get("BeamName")) is not None else None,
        treatment_machine_name=(
            str(value) if (value := beam_item.get("TreatmentMachineName")) is not None else None
        ),
        radiation_type=str(value) if (value := beam_item.get("RadiationType")) is not None else None,
        beam_type=str(value) if (value := beam_item.get("BeamType")) is not None else None,
        treatment_delivery_type=(
            str(value) if (value := beam_item.get("TreatmentDeliveryType")) is not None else None
        ),
        nominal_beam_energy=energy,
        gantry_angle=gantry,
        collimator_angle=collimator,
        couch_angle=couch,
        referenced_beam_number=reference["referenced_beam_number"] if reference else None,
        beam_dose=reference["beam_dose"] if reference else None,
        beam_meterset=reference["beam_meterset"] if reference else None,
    )


def parse_rtplan(dataset: Dataset) -> PlanInfo:
    """Parse an RTPLAN dataset into warning-aware, null-safe metadata."""
    context = "RTPLAN"
    warnings: list[str] = []

    def get_str(attribute: str) -> str | None:
        value = _get_attribute(dataset, attribute, context, warnings)
        return str(value) if value is not None else None

    if "BeamSequence" not in dataset:
        raise MissingRequiredAttributeError(
            f"{context}: BeamSequence is required but absent; the plan cannot be parsed without beam data."
        )

    dose_references: dict[int, dict[str, Any]] = {}
    number_of_fractions: int | None = None
    number_of_beams: int | None = None
    if "FractionGroupSequence" in dataset and len(dataset.FractionGroupSequence) > 0:
        fraction_group = dataset.FractionGroupSequence[0]
        number_of_fractions = _as_int(
            _get_attribute(fraction_group, "NumberOfFractionsPlanned", context, warnings)
        )
        number_of_beams = _as_int(_get_attribute(fraction_group, "NumberOfBeams", context, warnings))
        if "ReferencedBeamSequence" in fraction_group:
            for referenced_beam in fraction_group.ReferencedBeamSequence:
                number = _as_int(referenced_beam.get("ReferencedBeamNumber"))
                if number is None:
                    warnings.append(
                        f"{context}: ReferencedBeamSequence item is missing 'ReferencedBeamNumber'; skipped."
                    )
                    continue
                dose_references[number] = {
                    "referenced_beam_number": number,
                    "beam_dose": _as_float(referenced_beam.get("BeamDose")),
                    "beam_meterset": _as_float(referenced_beam.get("BeamMeterset")),
                }
        else:
            warnings.append(
                f"{context}: 'ReferencedBeamSequence' is missing in the first fraction group; "
                "dose-reference linkage unavailable."
            )
    else:
        warnings.append(
            f"{context}: 'FractionGroupSequence' is missing; fractionation and "
            "dose-reference linkage unavailable."
        )

    beams = [_parse_plan_beam(beam_item, dose_references, warnings) for beam_item in dataset.BeamSequence]
    if number_of_beams is None:
        number_of_beams = len(beams)  # factual count, not an invented value

    prescription_dose: float | None = None
    if "DoseReferenceSequence" in dataset and len(dataset.DoseReferenceSequence) > 0:
        dose_reference = dataset.DoseReferenceSequence[0]
        prescription_dose = _as_float(dose_reference.get("TargetPrescriptionDose"))
        if prescription_dose is None:
            warnings.append(
                f"{context}: 'TargetPrescriptionDose' is missing in the first dose reference; value set to null."
            )
    else:
        warnings.append(f"{context}: 'DoseReferenceSequence' is missing; prescription dose set to null.")

    structure_set_uid: str | None = None
    if "ReferencedStructureSetSequence" in dataset and len(dataset.ReferencedStructureSetSequence) > 0:
        structure_set_uid = str(
            dataset.ReferencedStructureSetSequence[0].get("ReferencedSOPInstanceUID") or ""
        ) or None
        if structure_set_uid is None:
            warnings.append(
                f"{context}: 'ReferencedSOPInstanceUID' is missing in the structure set reference; "
                "value set to null."
            )
    else:
        warnings.append(
            f"{context}: 'ReferencedStructureSetSequence' is missing; structure set linkage set to null."
        )

    return PlanInfo(
        plan_label=get_str("RTPlanLabel"),
        plan_name=get_str("RTPlanName"),
        plan_date=get_str("RTPlanDate"),
        approval_status=get_str("ApprovalStatus"),
        number_of_fractions=number_of_fractions,
        number_of_beams=number_of_beams,
        prescription_dose=prescription_dose,
        referenced_structure_set_sop_uid=structure_set_uid,
        beams=beams,
        parser="pydicom",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# RTSTRUCT parsing
# ---------------------------------------------------------------------------
def parse_rtstruct(dataset: Dataset) -> StructureInfo:
    """Parse an RTSTRUCT dataset into warning-aware, null-safe ROI summaries."""
    context = "RTSTRUCT"
    warnings: list[str] = []

    def get_str(attribute: str) -> str | None:
        value = _get_attribute(dataset, attribute, context, warnings)
        return str(value) if value is not None else None

    if "StructureSetROISequence" not in dataset:
        raise MissingRequiredAttributeError(
            f"{context}: StructureSetROISequence is required but absent."
        )

    contour_counts: dict[int, int] = {}
    if "ROIContourSequence" in dataset:
        for contour_roi in dataset.ROIContourSequence:
            roi_number = _as_int(contour_roi.get("ReferencedROINumber"))
            if roi_number is None:
                warnings.append(
                    f"{context}: ROIContourSequence item is missing 'ReferencedROINumber'; skipped."
                )
                continue
            if "ContourSequence" in contour_roi:
                contour_counts[roi_number] = len(contour_roi.ContourSequence)
            else:
                warnings.append(
                    f"{context} ROI {roi_number}: 'ContourSequence' is missing; contour count set to null."
                )
    else:
        warnings.append(f"{context}: 'ROIContourSequence' is missing; contour counts set to null.")

    interpreted_types: dict[int, str] = {}
    if "RTROIObservationsSequence" in dataset:
        for observation in dataset.RTROIObservationsSequence:
            roi_number = _as_int(observation.get("ReferencedROINumber"))
            interpreted = observation.get("RTROIInterpretedType")
            if roi_number is not None and interpreted is not None:
                interpreted_types[roi_number] = str(interpreted)
    else:
        warnings.append(
            f"{context}: 'RTROIObservationsSequence' is missing; ROI interpreted types unavailable."
        )

    rois: list[RoiSummary] = []
    for roi_item in dataset.StructureSetROISequence:
        roi_number = _as_int(roi_item.get("ROINumber"))
        if roi_number is None:
            warnings.append(f"{context}: StructureSetROISequence item is missing 'ROINumber'; skipped.")
            continue
        roi_context = f"{context} ROI {roi_number}"
        raw_name = _get_attribute(roi_item, "ROIName", roi_context, warnings)
        roi_name = str(raw_name) if raw_name is not None else None
        roi_type = interpreted_types.get(roi_number)
        if roi_type is None and "ROIGenerationAlgorithm" in roi_item:
            roi_type = str(roi_item.ROIGenerationAlgorithm)
        if roi_number not in contour_counts and "ROIContourSequence" in dataset:
            warnings.append(
                f"{roi_context}: no matching item in ROIContourSequence; contour count set to null."
            )
        rois.append(
            RoiSummary(
                roi_number=roi_number,
                roi_name=roi_name,
                roi_type=roi_type,
                contour_count=contour_counts.get(roi_number),
            )
        )

    parser = "pydicom"
    if DICOMPYLER_AVAILABLE:
        try:
            structures = dicomparser.DicomParser(dataset).GetStructures()
            for roi in rois:
                if roi.roi_type is None and roi.roi_number in structures:
                    roi.roi_type = structures[roi.roi_number].get("type") or None
            parser = "pydicom+dicompyler-core"
        except Exception as exc:  # noqa: BLE001 - enrichment must degrade safely
            warnings.append(
                f"{context}: dicompyler-core structure enrichment unavailable "
                f"({type(exc).__name__}); using pydicom fallback."
            )
    else:
        warnings.append(
            f"{context}: dicompyler-core is not available "
            f"({_DICOMPYLER_IMPORT_ERROR}); using pydicom fallback."
        )

    return StructureInfo(
        structure_set_label=get_str("StructureSetLabel"),
        structure_set_date=get_str("StructureSetDate"),
        rois=rois,
        roi_count=len(rois),
        parser=parser,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# RTDOSE parsing
# ---------------------------------------------------------------------------
def _scaled_attribute(
    item: Dataset, attribute: str, scaling: float | None, context: str, warnings: list[str]
) -> float | None:
    if attribute not in item:
        warnings.append(_missing_warning(attribute, context))
        return None
    if scaling is None:
        warnings.append(f"{context}: cannot scale '{attribute}' because DVHDoseScaling is missing.")
        return None
    return _as_float(item[attribute].value) * scaling


def _parse_dvh_item(
    dataset: Dataset, item: Dataset, roi_number: int | None, warnings: list[str]
) -> tuple[DvhSeries, bool]:
    context = f"RTDOSE DVH for ROI {roi_number if roi_number is not None else '?'}"
    used_dicompyler = False

    dvh_type = str(value) if (value := item.get("DVHType")) is not None else None
    # DVH items reuse the shared DoseUnits/DoseType keywords (3004,0002)/(3004,0004).
    dose_units = str(value) if (value := item.get("DoseUnits")) is not None else None
    dose_type = str(value) if (value := item.get("DoseType")) is not None else None
    volume_units = str(value) if (value := item.get("DVHVolumeUnits")) is not None else None
    scaling = _as_float(item.get("DVHDoseScaling"))
    if "DVHDoseScaling" not in item:
        warnings.append(_missing_warning("DVHDoseScaling", context))

    dose_bins: list[float] | None = None
    volumes: list[float] | None = None
    number_of_bins = _as_int(item.get("DVHNumberOfBins"))
    data = item.get("DVHData")
    if data is None:
        warnings.append(f"{context}: 'DVHData' is missing; dose and volume series set to null.")
    else:
        raw_dose_values = [float(value) for value in data[0::2]]
        volumes = [float(value) for value in data[1::2]]
        if scaling is None:
            warnings.append(f"{context}: DVHDoseScaling is missing; dose bins set to null.")
        else:
            dose_bins = [dose * scaling for dose in raw_dose_values]
        if number_of_bins is None:
            number_of_bins = len(volumes)
        if dose_bins is not None and len(dose_bins) > _DVH_MAX_BIN_COUNT:
            warnings.append(
                f"{context}: DVH truncated from {len(dose_bins)} to {_DVH_MAX_BIN_COUNT} bins for display."
            )
            dose_bins = dose_bins[:_DVH_MAX_BIN_COUNT]
            volumes = volumes[:_DVH_MAX_BIN_COUNT]

    min_dose: float | None = None
    max_dose: float | None = None
    mean_dose: float | None = None
    initial_volume: float | None = None

    if DICOMPYLER_AVAILABLE and roi_number is not None and scaling is not None:
        try:
            dvh_object = dvh_module.DVH.from_dicom_dvh(dataset, roi_number)
            used_dicompyler = True
            initial_volume = _nan_to_none(dvh_object.volume)
            min_dose = _nan_to_none(dvh_object.min)
            max_dose = _nan_to_none(dvh_object.max)
            mean_dose = _nan_to_none(dvh_object.mean)
        except Exception as exc:  # noqa: BLE001 - DVH stats must degrade safely
            used_dicompyler = False
            warnings.append(
                f"{context}: dicompyler-core DVH statistics unavailable ({type(exc).__name__}); "
                "falling back to declared DVH attributes."
            )

    if not used_dicompyler:
        min_dose = _scaled_attribute(item, "DVHMinimumDose", scaling, context, warnings)
        max_dose = _scaled_attribute(item, "DVHMaximumDose", scaling, context, warnings)
        mean_dose = _scaled_attribute(item, "DVHMeanDose", scaling, context, warnings)
        initial_volume = volumes[0] if volumes else None

    series = DvhSeries(
        roi_number=roi_number,
        dvh_type=dvh_type,
        dose_units=dose_units,
        dose_type=dose_type,
        volume_units=volume_units,
        number_of_bins=number_of_bins,
        dose_bins=dose_bins,
        volumes=volumes,
        initial_volume=initial_volume,
        min_dose=min_dose,
        max_dose=max_dose,
        mean_dose=mean_dose,
    )
    return series, used_dicompyler


def parse_rtdose(dataset: Dataset) -> DoseInfo:
    """Parse an RTDOSE dataset into warning-aware, null-safe metadata and DVH."""
    context = "RTDOSE"
    warnings: list[str] = []

    dose_units = str(value) if (value := _get_attribute(dataset, "DoseUnits", context, warnings)) is not None else None
    dose_type = str(value) if (value := _get_attribute(dataset, "DoseType", context, warnings)) is not None else None
    dose_summation_type = (
        str(value)
        if (value := _get_attribute(dataset, "DoseSummationType", context, warnings)) is not None
        else None
    )

    rows = _as_int(_get_attribute(dataset, "Rows", context, warnings))
    columns = _as_int(_get_attribute(dataset, "Columns", context, warnings))
    number_of_frames = _as_int(_get_attribute(dataset, "NumberOfFrames", context, warnings))
    pixel_spacing = _as_float_list(_get_attribute(dataset, "PixelSpacing", context, warnings))
    image_position_patient = _as_float_list(_get_attribute(dataset, "ImagePositionPatient", context, warnings))
    dose_grid_scaling = _as_float(_get_attribute(dataset, "DoseGridScaling", context, warnings))
    if "GridFrameOffsetVector" in dataset:
        grid_frame_offset_count = len(dataset.GridFrameOffsetVector)
    else:
        grid_frame_offset_count = None
        warnings.append(_missing_warning("GridFrameOffsetVector", context))
    grid = DoseGridInfo(
        rows=rows,
        columns=columns,
        number_of_frames=number_of_frames,
        pixel_spacing=pixel_spacing,
        image_position_patient=image_position_patient,
        dose_grid_scaling=dose_grid_scaling,
        grid_frame_offset_count=grid_frame_offset_count,
    )

    dvh_series: list[DvhSeries] = []
    used_dicompyler = False
    if "DVHSequence" in dataset and len(dataset.DVHSequence) > 0:
        for item in dataset.DVHSequence:
            roi_number: int | None = None
            if "DVHReferencedROISequence" in item and len(item.DVHReferencedROISequence) > 0:
                roi_number = _as_int(item.DVHReferencedROISequence[0].get("ReferencedROINumber"))
            else:
                warnings.append(
                    f"{context}: DVH item is missing 'DVHReferencedROISequence'; ROI number set to null."
                )
            series, item_used_dicompyler = _parse_dvh_item(dataset, item, roi_number, warnings)
            used_dicompyler = used_dicompyler or item_used_dicompyler
            dvh_series.append(series)
    else:
        warnings.append(f"{context}: 'DVHSequence' is missing or empty; DVH data unavailable.")

    return DoseInfo(
        dose_units=dose_units,
        dose_type=dose_type,
        dose_summation_type=dose_summation_type,
        grid=grid,
        has_dvh=len(dvh_series) > 0,
        dvh=dvh_series,
        parser="pydicom+dicompyler-core" if used_dicompyler else "pydicom",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Byte-level entry point and synthetic demo case
# ---------------------------------------------------------------------------
def parse_dataset_bytes(data: bytes) -> tuple[str, AnalysisResult]:
    """Detect and parse an uploaded DICOM-RT file.

    Returns ``(rt_object_type, AnalysisResult)``. Raises typed errors for
    malformed input, unidentifiable datasets, and unsupported modalities.
    Pixel data is never read.
    """
    try:
        dataset = dcmread(BytesIO(data), force=True, stop_before_pixels=True)
    except InvalidDicomError as exc:
        raise InvalidDICOMError("Uploaded file is not a valid DICOM file.") from exc
    except Exception as exc:  # noqa: BLE001 - any pydicom failure maps to a typed error
        raise InvalidDICOMError(
            f"Uploaded file could not be parsed as DICOM ({type(exc).__name__})."
        ) from exc

    if dataset is None or (dataset.get("Modality") is None and dataset.get("SOPClassUID") is None):
        raise InvalidDICOMError("Uploaded file does not contain a DICOM dataset.")

    rt_object_type = detect_rt_object(dataset)
    warnings: list[str] = []
    plan: PlanInfo | None = None
    structures: StructureInfo | None = None
    dose: DoseInfo | None = None

    if rt_object_type == "RTPLAN":
        plan = parse_rtplan(dataset)
        warnings = plan.warnings
    elif rt_object_type == "RTSTRUCT":
        structures = parse_rtstruct(dataset)
        warnings = structures.warnings
    else:
        dose = parse_rtdose(dataset)
        warnings = dose.warnings

    return rt_object_type, AnalysisResult(
        rt_object_type=rt_object_type,
        source="upload",
        structures=structures,
        plan=plan,
        dose=dose,
        warnings=warnings,
        errors=[],
    )


def run_synthetic_demo_case() -> AnalysisResult:
    """Run the deterministic synthetic demo case (no upload required)."""
    plan_dataset, structure_dataset, dose_dataset = build_synthetic_datasets()
    plan = parse_rtplan(plan_dataset)
    structures = parse_rtstruct(structure_dataset)
    dose = parse_rtdose(dose_dataset)

    warnings = [*plan.warnings, *structures.warnings, *dose.warnings]
    roi_names = {roi.roi_number: roi.roi_name for roi in structures.rois}
    for series in dose.dvh:
        if series.roi_number in roi_names:
            series.roi_name = roi_names[series.roi_number]

    return AnalysisResult(
        rt_object_type="DEMO_CASE",
        source="demo_case",
        structures=structures,
        plan=plan,
        dose=dose,
        warnings=warnings,
        errors=[],
    )
