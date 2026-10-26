# Testing (docs/testing.md)

Run everything with:

```bash
uv run pytest          # all tests (unit + integration)
uv run pytest tests/unit
uv run pytest tests/integration
uv run ruff check .
```

Integration tests run against an isolated temporary SQLite database configured in `tests/conftest.py` (`RTQA_DATABASE_URL`), so they never touch `data/dicomrt.db`.

## Test matrix

| # | Layer | Test | What it proves |
| --- | --- | --- | --- |
| 1 | unit | `test_dataset_build_is_deterministic` | two builds produce byte-identical datasets |
| 2 | unit | `test_uids_are_stable_across_builds` | deterministic UID generation (no randomness) |
| 3 | unit | `test_plan_constants_are_internally_consistent` | 1.0 Gy x 2 beams x 30 fx = 60 Gy prescription |
| 4 | unit | `test_plan_dataset_matches_constants` | RTPLAN structure matches named constants |
| 5 | unit | `test_struct_dataset_matches_definitions` | ROI names + contour counts match constants |
| 6 | unit | `test_dose_dataset_grid_and_dvh_shape` | dose grid + DVH pair structure |
| 7 | unit | `test_dataset_to_bytes_roundtrip` | dataset -> DICOM bytes -> dataset roundtrip |
| 8 | unit | `test_demo_case_is_deterministic` | full demo result identical across runs |
| 9 | unit | `test_demo_case_dvh_links_to_struct_roi_name` | DVH ROI name joined from structure set |
| 10 | unit | `test_detect_rt_object_*` | RTPLAN/RTSTRUCT/RTDOSE detection; invalid -> typed error |
| 11 | unit | `test_parse_rtplan_beam_metadata` | beams, machine, energy, angles, dose-reference linkage |
| 12 | unit | `test_missing_plan_fields_become_null_with_warnings` | nulls + warnings for RTPlanName/GantryAngle/FractionGroupSequence |
| 13 | unit | `test_rtplan_without_beam_sequence_raises_typed_error` | `MissingRequiredAttributeError` |
| 14 | unit | `test_parse_rtstruct_rois` | ROI numbers, names, types, contour counts |
| 15 | unit | `test_rtstruct_without_roi_sequence_raises_typed_error` | `MissingRequiredAttributeError` |
| 16 | unit | `test_missing_struct_fields_become_null_with_warnings` | nulls + warnings for ROIName/ROIContourSequence |
| 17 | unit | `test_parse_rtdose_grid_and_dvh` | units, grid, DVH bins/volumes, derived stats |
| 18 | unit | `test_rtdose_without_dvh_sequence_warns_and_degrades` | empty state, no crash |
| 19 | unit | `test_rtdose_missing_grid_fields_become_null_with_warnings` | null + warning for PixelSpacing |
| 20 | unit | `test_malformed_bytes_raise_invalid_dicom_error` / `test_empty_bytes_*` | typed 400-class failure |
| 21 | unit | `test_unsupported_rt_object_raises_typed_error` | CT file -> `UnsupportedRTObjectError` |
| 22 | unit | `test_error_taxonomy_hierarchy` | all four errors subclass `RTQAError` |
| 23 | unit | `test_parse_dataset_bytes_rtplan_roundtrip` | upload path returns upload-sourced result |
| 24 | integ | `test_demo_case_creates_analysis_and_audit_record` | persistence of record + `AuditEvent` |
| 25 | integ | `test_demo_case_plan_endpoint_returns_beam_data` | synthetic plan inspection endpoint |
| 26 | integ | `test_analysis_history_returns_persisted_records` | history API returns persisted rows |
| 27 | integ | `test_repeated_demo_runs_create_separate_records` | two runs -> two distinct records (+2 count) |
| 28 | integ | `test_get_single_analysis_and_structured_404` | detail payload + structured 404 envelope |
| 29 | integ | `test_analysis_plan_endpoint_returns_available_plan` | per-analysis plan endpoint |
| 30 | integ | `test_invalid_upload_returns_structured_400` | `error.class == InvalidDICOMError`, trace id present |
| 31 | integ | `test_unsupported_upload_returns_structured_400` | CT -> structured 400 |
| 32 | integ | `test_uploaded_rtplan_is_parsed_and_persisted` | full upload -> parse -> persist loop |
| 33 | integ | `test_failed_upload_is_persisted_for_audit` | failed parse stored with `status=failed` |
| 34 | integ | `test_health_endpoint_checks_database_connectivity` | `/health` reflects DB state |
| 35 | integ | `test_metrics_endpoint_exposes_expected_metric_names` | all four metric families exposed |

## Unit versus integration

- **Unit tests** exercise the domain engine and synthetic data with no server and no database. They delete DICOM attributes deliberately to prove the "null + warning" contract and assert exact typed errors.
- **Integration tests** boot the real FastAPI app via `TestClient` (lifespan included) against a temp SQLite file and verify end-to-end behaviour: persistence, audit events, pagination, error envelopes, health, and metrics.

## Manual reviewer checklist

1. `uv sync` then `uv run pytest` - expect "37 passed".
2. `uv run ruff check .` - expect "All checks passed!".
3. Start API + dashboard (two terminals), open <http://localhost:8501>:
   - safety notice visible; **Load demo case** populates all tabs;
   - Structures/Plan/Dose tabs show tables; set a field to "null" awareness (see warnings);
   - History shows records, survives a browser refresh;
   - History shows separate rows for repeated demo runs.
4. Upload a non-DICOM file (e.g. a `.txt` renamed `.dcm`) - expect a structured error message, and a `failed` row in History.
5. Open `/docs`, `/health`, `/metrics` - all respond; metrics include the four `rtqa_*` families.
6. `docker compose up --build` - both services healthy; repeat step 3 against :8501.
