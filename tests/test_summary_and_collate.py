"""The summary both composition paths share, and the collation that fits the cost model."""

from __future__ import annotations

from typing import Any

import pytest

from etno_twin.kernel.config import ExperimentConfig
from etno_twin.kernel.summary import summarise, summary_columns, weighted_summary
from etno_twin.stages.collate import _peak_rss, fit_cost_model

AU_KM = 1.495978707e8


def _detection(obj_id: str, magnitude: float, distance_au: float) -> dict[str, str]:
    return {
        "ObjID": obj_id,
        "trailedSourceMag": str(magnitude),
        "Range_LTC_km": str(distance_au * AU_KM),
    }


def test_an_empty_catalogue_summarises_to_zeros(fake_experiment: ExperimentConfig) -> None:
    summary = summarise(fake_experiment, [])
    assert set(summary) == set(summary_columns(fake_experiment))
    assert all(value == 0.0 for value in summary.values())


def test_counts_land_in_the_configured_bins(fake_experiment: ExperimentConfig) -> None:
    # Configured magnitude edges are 21.0, 22.5, 24.0 — four bins including both overflows.
    summary = summarise(
        fake_experiment,
        [
            _detection("a", 20.0, 45.0),
            _detection("a", 23.0, 45.0),
            _detection("b", 25.0, 200.0),
        ],
    )
    assert summary["x_n_detected_objects"] == 2.0
    assert summary["x_n_detections"] == 3.0
    assert summary["x_mag_bin_00"] == 1.0
    assert summary["x_mag_bin_02"] == 1.0
    assert summary["x_mag_bin_03"] == 1.0


def test_uniform_weights_reproduce_the_plain_summary(fake_experiment: ExperimentConfig) -> None:
    """The reweighted path and the simulated path must summarise identically, or the
    comparison between them measures the difference between two summaries."""
    detections = [
        _detection("a", 21.5, 60.0),
        _detection("a", 22.0, 61.0),
        _detection("b", 23.5, 95.0),
    ]
    plain = summarise(fake_experiment, detections)
    weighted = weighted_summary(
        fake_experiment, detections, {"a": 1.0, "b": 1.0, "c": 1.0}, scale_to_objects=3.0
    )
    for column in summary_columns(fake_experiment):
        assert weighted[column] == pytest.approx(plain[column])


def test_an_excluded_object_drops_out_of_the_composed_catalogue(
    fake_experiment: ExperimentConfig,
) -> None:
    detections = [_detection("a", 21.5, 60.0), _detection("b", 23.5, 95.0)]
    weighted = weighted_summary(
        fake_experiment, detections, {"a": 1.0, "b": 0.0}, scale_to_objects=2.0
    )
    assert weighted["x_n_detected_objects"] == pytest.approx(2.0)
    assert weighted["x_n_detections"] == pytest.approx(2.0)
    assert weighted["x_mag_bin_03"] == 0.0


def test_a_library_with_no_usable_weight_composes_to_zeros(
    fake_experiment: ExperimentConfig,
) -> None:
    weighted = weighted_summary(
        fake_experiment, [_detection("a", 21.5, 60.0)], {"a": 0.0}, scale_to_objects=5.0
    )
    assert all(value == 0.0 for value in weighted.values())


def _campaign_manifest(
    label: str,
    n_objects: int,
    wall: float,
    warmup: bool = False,
    peak_rss: int = 700_000_000,
    reliable: bool = True,
) -> dict[str, Any]:
    return {
        "stage": "campaign",
        "parameters": {"label": label, "binding": "sorcha"},
        "measurements": {
            "warmup": warmup,
            "n_objects": n_objects,
            "process": {
                "wall_seconds": wall,
                "peak_rss_bytes": peak_rss,
                "peak_rss_source": "proc_vm_hwm",
                "peak_rss_reliable": reliable,
            },
            "detection_efficiency": {
                "n_objects": n_objects,
                "n_objects_detected": 1,
                "fraction_objects_detected": 1.0 / n_objects,
                "n_detections": 30,
                "detections_per_object": 30.0 / n_objects,
            },
            "fixed_cost_from_log": {
                "applicable": True,
                "fixed_seconds": 13.9,
                "size_independent_seconds": 11.8,
                "interpreter_startup_seconds": 2.1,
                "size_independent_phases": ["startup", "pointing_database", "ephemeris_setup"],
            },
        },
    }


def test_the_cost_model_recovers_fixed_and_marginal_cost_from_a_sweep() -> None:
    runs = [_campaign_manifest(f"sweep-n{n}-rep0", n, 14.0 + 1.4 * n) for n in (10, 100, 1000)]
    fit = fit_cost_model(runs)["fit"]
    assert fit["available"]
    assert fit["fixed_seconds"] == pytest.approx(14.0)
    assert fit["marginal_seconds_per_object"] == pytest.approx(1.4)


def test_a_single_population_size_reports_why_it_cannot_fit() -> None:
    summary = fit_cost_model([_campaign_manifest("sweep-n10-rep0", 10, 28.4)])
    assert not summary["fit"]["available"]
    assert "two distinct population sizes" in summary["fit"]["reason"]


def test_warmup_runs_are_recorded_and_excluded_from_the_fit() -> None:
    runs = [
        _campaign_manifest("warmup-0", 10, 45.0, warmup=True),
        *[_campaign_manifest(f"sweep-n{n}-rep0", n, 14.0 + 1.4 * n) for n in (10, 100)],
    ]
    summary = fit_cost_model(runs)
    assert [entry["label"] for entry in summary["warmup_runs_excluded"]] == ["warmup-0"]
    assert summary["fit"]["fixed_seconds"] == pytest.approx(14.0)


def test_repetitions_are_reduced_by_their_median() -> None:
    runs = [
        _campaign_manifest("sweep-n10-rep0", 10, 28.0),
        _campaign_manifest("sweep-n10-rep1", 10, 29.0),
        _campaign_manifest("sweep-n10-rep2", 10, 99.0),
        _campaign_manifest("sweep-n100-rep0", 100, 154.0),
        _campaign_manifest("sweep-n100-rep1", 100, 156.0),
    ]
    points = {
        point["n_objects"]: point["median_wall_seconds"] for point in fit_cost_model(runs)["points"]
    }
    assert points[10] == pytest.approx(29.0), "one descheduled run must not move the estimate"


def test_the_two_estimates_of_fixed_cost_are_reported_side_by_side() -> None:
    runs = [_campaign_manifest(f"sweep-n{n}-rep0", n, 14.0 + 1.4 * n) for n in (10, 100, 1000)]
    summary = fit_cost_model(runs)
    assert summary["fixed_cost_from_log"]["available"]
    assert summary["fixed_cost_agreement"]["from_sweep_seconds"] == pytest.approx(14.0)
    assert summary["fixed_cost_agreement"]["from_log_seconds"] == pytest.approx(13.9)
    assert abs(summary["fixed_cost_agreement"]["difference_seconds"]) < 0.2


def test_the_worker_memory_footprint_is_the_largest_measured_run() -> None:
    runs = [
        _campaign_manifest("draw-0000", 10, 28.0, peak_rss=700_000_000),
        _campaign_manifest("draw-0001", 10, 28.0, peak_rss=740_000_000),
    ]
    summary = _peak_rss(runs)
    assert summary["available"]
    assert summary["max"] == 740_000_000
    assert summary["n_runs_excluded_as_too_short"] == 0


def test_a_run_too_short_to_sample_is_excluded_not_averaged_in() -> None:
    """Its figure is an underestimate taken before the process allocated anything."""
    runs = [
        _campaign_manifest("draw-0000", 10, 28.0, peak_rss=740_000_000),
        _campaign_manifest("draw-0001", 10, 0.04, peak_rss=725_000, reliable=False),
    ]
    summary = _peak_rss(runs)
    assert summary["max"] == 740_000_000
    assert summary["n_runs_excluded_as_too_short"] == 1


def test_a_campaign_of_only_short_runs_reports_no_memory_figure() -> None:
    runs = [_campaign_manifest("draw-0000", 10, 0.04, peak_rss=725_000, reliable=False)]
    summary = _peak_rss(runs)
    assert not summary["available"]
    assert "underestimates" in summary["reason"]
