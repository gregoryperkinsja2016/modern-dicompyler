"""Deterministic synthetic DICOM-RT datasets for the demo case.

Every value in this module is a named constant. No random number generation
and no wall-clock input is used, so identical datasets (and therefore an
identical analysis result) are produced on every call.

The internal dose calculation is consistent by construction:
``BEAM_DOSE_GY x len(BEAM_METESETS_MU) x PLAN_NUMBER_OF_FRACTIONS ==
PRESCRIPTION_DOSE_GY`` (1.0 Gy x 2 beams x 30 fractions = 60 Gy).

All identity values are clearly synthetic (patient id ``SYNTH-0001``,
machine ``SYNTH-LINAC-01``) and never represent real patient data.
"""
from __future__ import annotations

from io import BytesIO

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import (
    ImplicitVRLittleEndian,
    RTDoseStorage,
    RTPlanStorage,
    RTStructureSetStorage,
    generate_uid,
)

# ---------------------------------------------------------------------------
# Identity constants (stable across runs -> deterministic UIDs)
# ---------------------------------------------------------------------------
SYNTHETIC_NAMESPACE = "modern-dicompyler/synthetic/v1"
SYNTHETIC_PATIENT_ID = "SYNTH-0001"
SYNTHETIC_STUDY_DATE = "20240101"
SYNTHETIC_STUDY_TIME = "000000"
SYNTHETIC_SERIES_NUMBER = 1

SYNTHETIC_STUDY_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "study"])
FRAME_OF_REFERENCE_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "frame-of-reference"])
SYNTHETIC_PLAN_SOP_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "rtplan"])
SYNTHETIC_PLAN_SERIES_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "rtplan-series"])
SYNTHETIC_STRUCT_SOP_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "rtstruct"])
SYNTHETIC_STRUCT_SERIES_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "rtstruct-series"])
SYNTHETIC_DOSE_SOP_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "rtdose"])
SYNTHETIC_DOSE_SERIES_UID = generate_uid(entropy_srcs=[SYNTHETIC_NAMESPACE, "rtdose-series"])

# ---------------------------------------------------------------------------
# RTPLAN constants
# ---------------------------------------------------------------------------
PLAN_LABEL = "SYNTH-PLAN-01"
PLAN_NAME = "Synthetic Two-Field Plan"
PLAN_APPROVAL_STATUS = "UNAPPROVED"
PLAN_NUMBER_OF_FRACTIONS = 30
PRESCRIPTION_DOSE_GY = 60.0
PLAN_NUMBER_OF_BEAMS = 2
BEAM_ENERGY_MV = 6.0
BEAM_GANTRY_ANGLES_DEG = (0.0, 90.0)
BEAM_COLLIMATOR_ANGLE_DEG = 0.0
BEAM_COUCH_ANGLE_DEG = 0.0
TREATMENT_MACHINE_NAME = "SYNTH-LINAC-01"
RADIATION_TYPE = "PHOTON"
BEAM_TYPE = "STATIC"
TREATMENT_DELIVERY_TYPE = "TREATMENT"
FINAL_CUMULATIVE_METRESET_WEIGHT = 1.0
BEAM_DOSE_GY = 1.0  # per fraction, per beam
BEAM_METESETS_MU = (100.0, 120.0)

# ---------------------------------------------------------------------------
# RTSTRUCT constants
# ---------------------------------------------------------------------------
STRUCTURE_SET_LABEL = "SYNTH-STRUCT-01"
# (roi_number, roi_name, interpreted_type, generation_algorithm, contour_count)
ROI_DEFINITIONS = (
    (1, "SYNTH_BODY", "EXTERNAL", "SYNTHETIC", 4),
    (2, "SYNTH_PTV", "PTV", "SYNTHETIC", 6),
    (3, "SYNTH_OAR_01", "ORGAN", "SYNTHETIC", 3),
)
CONTOUR_SIDE_MM = 40.0
CONTOUR_SLICE_SPACING_MM = 5.0

# ---------------------------------------------------------------------------
# RTDOSE constants
# ---------------------------------------------------------------------------
DOSE_UNITS = "GY"
DOSE_TYPE = "PHYSICAL"
DOSE_SUMMATION_TYPE = "PLAN"
DOSE_GRID_ROWS = 16
DOSE_GRID_COLUMNS = 16
DOSE_GRID_FRAMES = 4
DOSE_GRID_PIXEL_SPACING_MM = (2.5, 2.5)
DOSE_GRID_SLICE_SPACING_MM = 2.5
DOSE_GRID_SCALING = 1e-6
DOSE_GRID_ORIGIN_MM = (-20.0, -20.0, 0.0)
_DOSE_PIXEL_MODULUS = 2000
_DOSE_PIXEL_STRIDE = 37

DVH_ROI_NUMBER = 2  # the synthetic PTV
DVH_NUMBER_OF_BINS = 20
DVH_DOSE_SCALING = 0.1
DVH_BIN_STEP_RAW = 5  # 5 * DVH_DOSE_SCALING = 0.5 Gy per bin edge
DVH_VOLUME_START_PERCENT = 100.0
DVH_VOLUME_FALLOFF_PERCENT_PER_BIN = 5.0
# Declared binned statistics (raw values scaled by DVH_DOSE_SCALING):
# min 2.5 Gy / max 10.0 Gy / mean 6.0 Gy.
DVH_MIN_DOSE_RAW = 25
DVH_MAX_DOSE_RAW = 100
DVH_MEAN_DOSE_RAW = 60


def _base_dataset(
    sop_class_uid: str,
    sop_instance_uid: str,
    modality: str,
    series_uid: str,
    series_description: str,
) -> Dataset:
    dataset = Dataset()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = sop_class_uid
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    dataset.file_meta = file_meta
    dataset.SpecificCharacterSet = "ISO_IR 100"
    dataset.SOPClassUID = sop_class_uid
    dataset.SOPInstanceUID = sop_instance_uid
    dataset.Modality = modality
    dataset.PatientID = SYNTHETIC_PATIENT_ID
    dataset.StudyInstanceUID = SYNTHETIC_STUDY_UID
    dataset.StudyDate = SYNTHETIC_STUDY_DATE
    dataset.StudyTime = SYNTHETIC_STUDY_TIME
    dataset.StudyID = "1"
    dataset.SeriesInstanceUID = series_uid
    dataset.SeriesNumber = SYNTHETIC_SERIES_NUMBER
    dataset.SeriesDescription = series_description
    return dataset


def build_synthetic_rtplan() -> Dataset:
    """Build a deterministic synthetic RTPLAN dataset with two beams."""
    dataset = _base_dataset(
        RTPlanStorage, SYNTHETIC_PLAN_SOP_UID, "RTPLAN", SYNTHETIC_PLAN_SERIES_UID, "Synthetic RT Plan"
    )
    dataset.RTPlanLabel = PLAN_LABEL
    dataset.RTPlanName = PLAN_NAME
    dataset.RTPlanDate = SYNTHETIC_STUDY_DATE
    dataset.RTPlanGeometry = "PATIENT"
    dataset.ApprovalStatus = PLAN_APPROVAL_STATUS

    structure_ref = Dataset()
    structure_ref.ReferencedSOPClassUID = RTStructureSetStorage
    structure_ref.ReferencedSOPInstanceUID = SYNTHETIC_STRUCT_SOP_UID
    dataset.ReferencedStructureSetSequence = Sequence([structure_ref])

    dose_reference = Dataset()
    dose_reference.DoseReferenceNumber = 1
    dose_reference.DoseReferenceStructureType = "SITE"
    dose_reference.TargetPrescriptionDose = PRESCRIPTION_DOSE_GY
    dataset.DoseReferenceSequence = Sequence([dose_reference])

    fraction_group = Dataset()
    fraction_group.FractionGroupNumber = 1
    fraction_group.NumberOfFractionsPlanned = PLAN_NUMBER_OF_FRACTIONS
    fraction_group.NumberOfBeams = PLAN_NUMBER_OF_BEAMS
    referenced_beams = []
    for beam_number, meterset in enumerate(BEAM_METESETS_MU, start=1):
        referenced_beam = Dataset()
        referenced_beam.ReferencedBeamNumber = beam_number
        referenced_beam.BeamDose = BEAM_DOSE_GY
        referenced_beam.BeamMeterset = meterset
        referenced_beams.append(referenced_beam)
    fraction_group.ReferencedBeamSequence = Sequence(referenced_beams)
    dataset.FractionGroupSequence = Sequence([fraction_group])

    beams = []
    for beam_number, gantry_angle in enumerate(BEAM_GANTRY_ANGLES_DEG, start=1):
        beam = Dataset()
        beam.BeamNumber = beam_number
        beam.BeamName = f"SYNTH-BEAM-{beam_number:02d}"
        beam.TreatmentMachineName = TREATMENT_MACHINE_NAME
        beam.RadiationType = RADIATION_TYPE
        beam.BeamType = BEAM_TYPE
        beam.TreatmentDeliveryType = TREATMENT_DELIVERY_TYPE
        beam.NumberOfWedges = 0
        beam.NumberOfCompensators = 0
        beam.NumberOfBoli = 0
        beam.NumberOfBlocks = 0
        beam.FinalCumulativeMetersetWeight = FINAL_CUMULATIVE_METRESET_WEIGHT
        beam.NumberOfControlPoints = 1
        control_point = Dataset()
        control_point.ControlPointIndex = 0
        control_point.NominalBeamEnergy = BEAM_ENERGY_MV
        control_point.GantryAngle = gantry_angle
        control_point.BeamLimitingDeviceAngle = BEAM_COLLIMATOR_ANGLE_DEG
        control_point.PatientSupportAngle = BEAM_COUCH_ANGLE_DEG
        control_point.CumulativeMetersetWeight = FINAL_CUMULATIVE_METRESET_WEIGHT
        beam.ControlPointSequence = Sequence([control_point])
        beams.append(beam)
    dataset.BeamSequence = Sequence(beams)
    return dataset


def _square_contour(z_mm: float) -> list[float]:
    half = CONTOUR_SIDE_MM / 2.0
    return [
        -half, -half, z_mm,
        half, -half, z_mm,
        half, half, z_mm,
        -half, half, z_mm,
        -half, -half, z_mm,
    ]


def build_synthetic_rtstruct() -> Dataset:
    """Build a deterministic synthetic RTSTRUCT dataset with three ROIs."""
    dataset = _base_dataset(
        RTStructureSetStorage,
        SYNTHETIC_STRUCT_SOP_UID,
        "RTSTRUCT",
        SYNTHETIC_STRUCT_SERIES_UID,
        "Synthetic RT Structure Set",
    )
    dataset.StructureSetLabel = STRUCTURE_SET_LABEL
    dataset.StructureSetDate = SYNTHETIC_STUDY_DATE

    frame_of_reference = Dataset()
    frame_of_reference.FrameOfReferenceUID = FRAME_OF_REFERENCE_UID
    dataset.ReferencedFrameOfReferenceSequence = Sequence([frame_of_reference])

    roi_items: list[Dataset] = []
    contour_roi_items: list[Dataset] = []
    observation_items: list[Dataset] = []
    for roi_number, roi_name, interpreted_type, algorithm, contour_count in ROI_DEFINITIONS:
        roi = Dataset()
        roi.ROINumber = roi_number
        roi.ReferencedFrameOfReferenceUID = FRAME_OF_REFERENCE_UID
        roi.ROIName = roi_name
        roi.ROIGenerationAlgorithm = algorithm
        roi_items.append(roi)

        contour_roi = Dataset()
        contour_roi.ReferencedROINumber = roi_number
        contours = []
        for contour_index in range(contour_count):
            contour = Dataset()
            contour.ContourGeometricType = "CLOSED_PLANAR"
            contour_data = _square_contour(contour_index * CONTOUR_SLICE_SPACING_MM)
            contour.NumberOfContourPoints = len(contour_data) // 3
            contour.ContourData = contour_data
            contours.append(contour)
        contour_roi.ContourSequence = Sequence(contours)
        contour_roi_items.append(contour_roi)

        observation = Dataset()
        observation.ObservationNumber = roi_number
        observation.ReferencedROINumber = roi_number
        observation.RTROIInterpretedType = interpreted_type
        observation_items.append(observation)

    dataset.StructureSetROISequence = Sequence(roi_items)
    dataset.ROIContourSequence = Sequence(contour_roi_items)
    dataset.RTROIObservationsSequence = Sequence(observation_items)
    return dataset


def _dvh_series_values() -> tuple[list[float], list[float]]:
    dose_bins = [
        (bin_index + 1) * DVH_BIN_STEP_RAW * DVH_DOSE_SCALING for bin_index in range(DVH_NUMBER_OF_BINS)
    ]
    volumes = [
        DVH_VOLUME_START_PERCENT - bin_index * DVH_VOLUME_FALLOFF_PERCENT_PER_BIN
        for bin_index in range(DVH_NUMBER_OF_BINS)
    ]
    return dose_bins, volumes


def build_synthetic_rtdose() -> Dataset:
    """Build a deterministic synthetic RTDOSE dataset with one cumulative DVH."""
    dataset = _base_dataset(
        RTDoseStorage, SYNTHETIC_DOSE_SOP_UID, "RTDOSE", SYNTHETIC_DOSE_SERIES_UID, "Synthetic RT Dose"
    )
    dataset.DoseUnits = DOSE_UNITS
    dataset.DoseType = DOSE_TYPE
    dataset.DoseSummationType = DOSE_SUMMATION_TYPE
    dataset.FrameOfReferenceUID = FRAME_OF_REFERENCE_UID
    dataset.Rows = DOSE_GRID_ROWS
    dataset.Columns = DOSE_GRID_COLUMNS
    dataset.NumberOfFrames = DOSE_GRID_FRAMES
    dataset.SamplesPerPixel = 1
    dataset.PixelSpacing = list(DOSE_GRID_PIXEL_SPACING_MM)
    dataset.ImagePositionPatient = list(DOSE_GRID_ORIGIN_MM)
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.SliceThickness = DOSE_GRID_SLICE_SPACING_MM
    dataset.GridFrameOffsetVector = [
        frame_index * DOSE_GRID_SLICE_SPACING_MM for frame_index in range(DOSE_GRID_FRAMES)
    ]
    dataset.DoseGridScaling = DOSE_GRID_SCALING
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0

    pixel_count = DOSE_GRID_ROWS * DOSE_GRID_COLUMNS * DOSE_GRID_FRAMES
    pixels = bytearray()
    for pixel_index in range(pixel_count):
        value = (pixel_index * _DOSE_PIXEL_STRIDE) % _DOSE_PIXEL_MODULUS
        pixels += value.to_bytes(2, byteorder="little")
    dataset.PixelData = bytes(pixels)

    plan_reference = Dataset()
    plan_reference.ReferencedSOPClassUID = RTPlanStorage
    plan_reference.ReferencedSOPInstanceUID = SYNTHETIC_PLAN_SOP_UID
    dataset.ReferencedRTPlanSequence = Sequence([plan_reference])

    dose_bins, volumes = _dvh_series_values()
    dvh_data = [value for pair in zip(dose_bins, volumes, strict=True) for value in pair]
    dvh_item = Dataset()
    # Note: DVH Sequence items reuse the shared 'DoseUnits'/'DoseType' keywords
    # (3004,0002)/(3004,0004) - there are no 'DVHDoseUnits'/'DVHDoseType' tags.
    dvh_item.DVHType = "CUMULATIVE"
    dvh_item.DoseUnits = DOSE_UNITS
    dvh_item.DoseType = DOSE_TYPE
    dvh_item.DVHVolumeUnits = "RELATIVE"
    dvh_item.DVHNumberOfBins = DVH_NUMBER_OF_BINS
    dvh_item.DVHDoseScaling = DVH_DOSE_SCALING
    dvh_item.DVHData = dvh_data
    dvh_item.DVHMinimumDose = DVH_MIN_DOSE_RAW
    dvh_item.DVHMaximumDose = DVH_MAX_DOSE_RAW
    dvh_item.DVHMeanDose = DVH_MEAN_DOSE_RAW
    referenced_roi = Dataset()
    referenced_roi.ReferencedROINumber = DVH_ROI_NUMBER
    dvh_item.DVHReferencedROISequence = Sequence([referenced_roi])
    dataset.DVHSequence = Sequence([dvh_item])
    return dataset


def build_synthetic_datasets() -> tuple[Dataset, Dataset, Dataset]:
    """Return the full synthetic case as ``(rtplan, rtstruct, rtdose)``."""
    return build_synthetic_rtplan(), build_synthetic_rtstruct(), build_synthetic_rtdose()


def dataset_to_bytes(dataset: Dataset) -> bytes:
    """Serialise a dataset to an in-memory DICOM file (Implicit VR Little Endian)."""
    import pydicom

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = dataset.SOPClassUID
    file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
    file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    dataset.file_meta = file_meta
    buffer = BytesIO()
    if int(pydicom.__version__.split(".")[0]) >= 3:
        dataset.save_as(buffer, enforce_file_format=True)
    else:
        dataset.is_little_endian = True
        dataset.is_implicit_VR = True
        dataset.save_as(buffer, write_like_original=False)
    return buffer.getvalue()
