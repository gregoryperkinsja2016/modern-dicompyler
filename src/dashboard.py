"""Streamlit dashboard for Modern Dicompyler.

This is the entire user interface of the project and it is Python-only:
it renders with Streamlit and talks to the FastAPI backend over HTTP using
``requests``. There is no JavaScript, React, Node, npm, Tailwind or Chart.js
anywhere in this project.

Run with:
    uv run streamlit run src/dashboard.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 10
HISTORY_PAGE_SIZE = 10

st.set_page_config(page_title="Modern Dicompyler", layout="wide")

st.title("Modern Dicompyler")
st.warning("Read-only demonstration viewer. Not for clinical plan verification.")


def _api_get(path: str, params: dict | None = None) -> requests.Response:
    return requests.get(f"{API_URL}{path}", params=params, timeout=REQUEST_TIMEOUT_SECONDS)


def _api_post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{API_URL}{path}", timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)


def _error_message(response: requests.Response) -> str:
    try:
        error = response.json().get("error", {})
        return f"{error.get('class', 'APIError')}: {error.get('message', response.text)}"
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"


def _format(value, suffix: str = "") -> str:
    return "null" if value is None else f"{value}{suffix}"


api_healthy = True
try:
    health_response = _api_get("/health")
    health = health_response.json()
    api_healthy = health_response.status_code == 200 and health.get("status") == "ok"
except requests.RequestException:
    health = None

with st.sidebar:
    st.header("Controls")
    if health is None:
        st.error(
            f"Cannot reach the API at {API_URL}. Start it with: "
            "`uv run uvicorn src.main:app --reload`"
        )
        api_healthy = False
    elif api_healthy:
        st.success(f"API healthy (database: {'up' if health.get('database') else 'down'})")
    else:
        st.error("API is reachable but reports an unhealthy state.")

    if st.button("Load demo case", type="primary", use_container_width=True, disabled=not api_healthy):
        with st.spinner("Running the deterministic synthetic demo case..."):
            try:
                response = _api_post("/api/v1/demo-case")
                if response.status_code >= 400:
                    st.error(_error_message(response))
                else:
                    st.session_state["analysis"] = response.json()
            except requests.RequestException as exc:
                st.error(f"API request failed: {exc}")

    uploaded = st.file_uploader("Upload a DICOM-RT file (.dcm)", type=["dcm"])
    if uploaded is not None and st.button(
        "Analyze uploaded file", use_container_width=True, disabled=not api_healthy
    ):
        with st.spinner("Parsing the uploaded DICOM-RT object..."):
            try:
                response = _api_post(
                    "/api/v1/analyses",
                    files={"file": (uploaded.name, uploaded.getvalue(), "application/dicom")},
                )
                if response.status_code >= 400:
                    st.error(_error_message(response))
                else:
                    st.session_state["analysis"] = response.json()
            except requests.RequestException as exc:
                st.error(f"API request failed: {exc}")

    st.caption("The demo case is deterministic, synthetic and contains no real patient data.")

analysis = st.session_state.get("analysis")
(
    overview_tab,
    structures_tab,
    plan_tab,
    dose_tab,
    history_tab,
) = st.tabs(["Overview", "Structures", "Plan", "Dose / DVH", "History"])


def _result_section(section: str) -> dict | None:
    if not analysis:
        return None
    result = analysis.get("result") or {}
    return result.get(section)


# ---------------------------------------------------------------------------
# Overview tab
# ---------------------------------------------------------------------------
with overview_tab:
    if not analysis:
        st.info("No analysis loaded yet. Use **Load demo case** or upload a DICOM-RT file.")
    else:
        left, middle, right = st.columns(3)
        analysis_id = analysis.get("analysis_id") or "n/a"
        left.metric("Analysis ID", analysis_id[:12] + "...")
        middle.metric("RT object type", str(analysis.get("rt_object_type") or "n/a"))
        right.metric("Created at", (analysis.get("created_at") or "n/a")[:19].replace("T", " "))

        analysis_warnings = analysis.get("warnings") or []
        if analysis_warnings:
            st.markdown("**Warnings**")
            for warning in analysis_warnings:
                st.markdown(f"- {warning}")
        else:
            st.success("No warnings.")

        analysis_errors = analysis.get("errors") or []
        if analysis_errors:
            st.error("Errors: " + "; ".join(analysis_errors))

        with st.expander("Full JSON response", expanded=False):
            st.json(analysis)

# ---------------------------------------------------------------------------
# Structures tab
# ---------------------------------------------------------------------------
with structures_tab:
    structures = _result_section("structures")
    if not structures or not structures.get("rois"):
        st.info(
            "No RTSTRUCT data available. Load the demo case or upload an RTSTRUCT file to "
            "inspect ROI information."
        )
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ROI number": roi.get("roi_number"),
                        "ROI name": roi.get("roi_name"),
                        "ROI type": roi.get("roi_type"),
                        "Contour count": roi.get("contour_count"),
                    }
                    for roi in structures.get("rois", [])
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"{structures.get('roi_count')} ROI(s) parsed with {structures.get('parser')}. "
            "null contour counts mean the ROI has no contour sequence."
        )
        structure_warnings = structures.get("warnings") or []
        if structure_warnings:
            with st.expander("Parsing warnings"):
                for warning in structure_warnings:
                    st.markdown(f"- {warning}")

# ---------------------------------------------------------------------------
# Plan tab
# ---------------------------------------------------------------------------
with plan_tab:
    plan = _result_section("plan")
    if not plan:
        st.info(
            "No RTPLAN data available. Load the demo case or upload an RTPLAN file to "
            "inspect plan and beam metadata."
        )
    else:
        metric_cols = st.columns(5)
        metric_cols[0].metric("Plan label", _format(plan.get("plan_label")))
        metric_cols[1].metric("Plan name", _format(plan.get("plan_name")))
        metric_cols[2].metric("Approval", _format(plan.get("approval_status")))
        metric_cols[3].metric("Fractions", _format(plan.get("number_of_fractions")))
        metric_cols[4].metric("Prescription (Gy)", _format(plan.get("prescription_dose")))

        beams = plan.get("beams") or []
        if not beams:
            st.info("No beams found in this RTPLAN (BeamSequence missing or empty).")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Beam number": beam.get("beam_number"),
                            "Beam name": beam.get("beam_name"),
                            "Treatment machine": beam.get("treatment_machine_name"),
                            "Radiation type": beam.get("radiation_type"),
                            "Beam type": beam.get("beam_type"),
                            "Energy (MV)": beam.get("nominal_beam_energy"),
                            "Gantry angle": beam.get("gantry_angle"),
                            "Collimator angle": beam.get("collimator_angle"),
                            "Couch angle": beam.get("couch_angle"),
                            "Dose-ref beam": beam.get("referenced_beam_number"),
                            "Beam dose (Gy)": beam.get("beam_dose"),
                            "Meterset (MU)": beam.get("beam_meterset"),
                        }
                        for beam in beams
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption("null means the DICOM attribute was missing (see parsing warnings).")
        plan_warnings = plan.get("warnings") or []
        if plan_warnings:
            with st.expander("Parsing warnings"):
                for warning in plan_warnings:
                    st.markdown(f"- {warning}")

# ---------------------------------------------------------------------------
# Dose / DVH tab
# ---------------------------------------------------------------------------
with dose_tab:
    dose = _result_section("dose")
    if not dose:
        st.info(
            "No RTDOSE data available. Load the demo case or upload an RTDOSE file to "
            "inspect dose metadata and DVH information."
        )
    else:
        dose_cols = st.columns(3)
        dose_cols[0].metric("Dose units", _format(dose.get("dose_units")))
        dose_cols[1].metric("Dose type", _format(dose.get("dose_type")))
        dose_cols[2].metric("Summation", _format(dose.get("dose_summation_type")))

        grid = dose.get("grid") or {}
        with st.expander("Dose grid information", expanded=True):
            st.markdown(
                f"- Rows: **{_format(grid.get('rows'))}**  |  Columns: "
                f"**{_format(grid.get('columns'))}**  |  Frames: **{_format(grid.get('number_of_frames'))}**"
            )
            st.markdown(
                f"- Pixel spacing (mm): **{_format(grid.get('pixel_spacing'))}**  |  "
                f"Origin (mm): **{_format(grid.get('image_position_patient'))}**"
            )
            st.markdown(
                f"- Dose grid scaling: **{_format(grid.get('dose_grid_scaling'))}**  |  "
                f"Grid frame offsets: **{_format(grid.get('grid_frame_offset_count'))}**"
            )

        dvh_list = dose.get("dvh") or []
        if not dose.get("has_dvh") or not dvh_list:
            st.info(
                "DVH data unavailable for this object (no DVH sequence present in the RTDOSE)."
            )
        else:
            for series in dvh_list:
                title = series.get("roi_name") or f"ROI {series.get('roi_number')}"
                dose_units = series.get("dose_units") or ""
                st.markdown(f"**DVH - {title}** ({dose_units} dose, {series.get('volume_units')} volume)")
                stats_cols = st.columns(4)
                stats_cols[0].metric("Min dose", _format(series.get("min_dose"), f" {dose_units}"))
                stats_cols[1].metric("Max dose", _format(series.get("max_dose"), f" {dose_units}"))
                stats_cols[2].metric("Mean dose", _format(series.get("mean_dose"), f" {dose_units}"))
                stats_cols[3].metric("Bins", _format(series.get("number_of_bins")))
                dose_bins = series.get("dose_bins")
                volumes = series.get("volumes")
                if dose_bins and volumes:
                    chart_frame = pd.DataFrame(
                        {"Volume": volumes},
                        index=pd.Index(dose_bins, name=f"Dose ({dose_units})"),
                    )
                    st.line_chart(chart_frame, height=240)
                else:
                    st.caption("Dose/volume series not available for this DVH.")
        dose_warnings = dose.get("warnings") or []
        if dose_warnings:
            with st.expander("Parsing warnings"):
                for warning in dose_warnings:
                    st.markdown(f"- {warning}")

# ---------------------------------------------------------------------------
# History tab
# ---------------------------------------------------------------------------
with history_tab:
    st.markdown(
        "Previous analyses are persisted in SQLite and survive browser refreshes."
    )
    page = st.session_state.get("history_page", 1)
    total_pages = st.session_state.get("history_total_pages", 1)
    nav_previous, nav_next, nav_info = st.columns([1, 1, 6])
    if nav_previous.button("Previous page", disabled=page <= 1):
        page -= 1
        st.session_state["history_page"] = page
    if nav_next.button("Next page", disabled=page >= total_pages):
        page += 1
        st.session_state["history_page"] = page
    nav_info.caption(f"Current page: {page}")

    if not api_healthy:
        st.warning("History requires a healthy API connection.")
    else:
        try:
            response = _api_get(
                "/api/v1/analyses", params={"page": page, "page_size": HISTORY_PAGE_SIZE}
            )
            if response.status_code >= 400:
                st.error(_error_message(response))
            else:
                payload = response.json()
                st.session_state["history_total_pages"] = payload.get("total_pages", 1)
                items = payload.get("items", [])
                if not items:
                    st.info("No analyses recorded yet. Load the demo case to create one.")
                else:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Analysis ID": item.get("analysis_id"),
                                    "Created at": (item.get("created_at") or "")[:19].replace("T", " "),
                                    "Type": item.get("rt_object_type"),
                                    "Status": item.get("status"),
                                    "Source": item.get("source"),
                                    "Warnings": item.get("warning_count"),
                                    "Errors": item.get("error_count"),
                                }
                                for item in items
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(
                        f"Page {payload.get('page')} of {payload.get('total_pages')} - "
                        f"{payload.get('total')} analysis record(s) in total."
                    )
        except requests.RequestException as exc:
            st.error(f"API request failed: {exc}")
