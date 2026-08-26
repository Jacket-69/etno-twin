"""How a detection catalogue becomes the vector the network sees.

Shared by the stage that composes the training dataset and the stage that composes
datasets by reweighting a library, because the two must produce the *same* summary of the
same catalogue — otherwise the comparison between simulating a parameter value and
reweighting towards it measures the difference between two summaries instead.

Only columns the simulator port declares meaningful in every binding are read. The bin
edges come from the experiment configuration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from etno_twin.kernel.config import ExperimentConfig

AU_KM = 1.495978707e8


def bin_index(value: float, edges: Sequence[float]) -> int:
    """Index of the half-open bin ``value`` falls in, with overflow bins at both ends."""
    for index, edge in enumerate(edges):
        if value < edge:
            return index
    return len(edges)


def summary_columns(config: ExperimentConfig) -> tuple[str, ...]:
    """Names of the feature vector, declared from the configuration."""
    magnitude = [
        f"x_mag_bin_{index:02d}" for index in range(len(config.dataset.magnitude_bins) + 1)
    ]
    distance = [
        f"x_dist_bin_{index:02d}" for index in range(len(config.dataset.distance_bins_au) + 1)
    ]
    return ("x_n_detected_objects", "x_n_detections", *magnitude, *distance)


def _assemble(
    config: ExperimentConfig,
    n_detected_objects: float,
    n_detections: float,
    magnitude_counts: Sequence[float],
    distance_counts: Sequence[float],
) -> dict[str, float]:
    summary: dict[str, float] = {
        "x_n_detected_objects": n_detected_objects,
        "x_n_detections": n_detections,
    }
    for index, count in enumerate(magnitude_counts):
        summary[f"x_mag_bin_{index:02d}"] = count
    for index, count in enumerate(distance_counts):
        summary[f"x_dist_bin_{index:02d}"] = count
    return summary


def summarise(
    config: ExperimentConfig, detections: Sequence[Mapping[str, str]]
) -> dict[str, float]:
    """Reduce one detection catalogue to the feature vector.

    A catalogue with no rows is a valid outcome, not an error: for parts of the parameter
    space the survey genuinely sees nothing, and a summary of zeros is the honest
    representation of that.
    """
    magnitude_counts = [0.0] * (len(config.dataset.magnitude_bins) + 1)
    distance_counts = [0.0] * (len(config.dataset.distance_bins_au) + 1)
    for row in detections:
        magnitude_counts[
            bin_index(float(row["trailedSourceMag"]), config.dataset.magnitude_bins)
        ] += 1
        distance_counts[
            bin_index(float(row["Range_LTC_km"]) / AU_KM, config.dataset.distance_bins_au)
        ] += 1
    return _assemble(
        config,
        float(len({row["ObjID"] for row in detections})),
        float(len(detections)),
        magnitude_counts,
        distance_counts,
    )


def weighted_summary(
    config: ExperimentConfig,
    detections: Sequence[Mapping[str, str]],
    weights: Mapping[str, float],
    scale_to_objects: float,
) -> dict[str, float]:
    """Summarise a library's detections as if they had been drawn at other parameters.

    Each detection contributes its object's importance weight instead of one, and the
    result is rescaled so that the total stands for a population of ``scale_to_objects``
    objects — which makes it directly comparable with a summary of a population simulated
    at those parameters from scratch.

    Objects the target parameters exclude carry weight zero, so they drop out of the
    composed catalogue exactly as they would have been absent from a fresh simulation.
    """
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        return _assemble(
            config,
            0.0,
            0.0,
            [0.0] * (len(config.dataset.magnitude_bins) + 1),
            [0.0] * (len(config.dataset.distance_bins_au) + 1),
        )
    factor = scale_to_objects / total_weight

    magnitude_counts = [0.0] * (len(config.dataset.magnitude_bins) + 1)
    distance_counts = [0.0] * (len(config.dataset.distance_bins_au) + 1)
    detected_weight = 0.0
    seen: set[str] = set()
    total_detections = 0.0
    for row in detections:
        obj_id = row["ObjID"]
        weight = weights.get(obj_id, 0.0)
        if weight <= 0.0:
            continue
        if obj_id not in seen:
            seen.add(obj_id)
            detected_weight += weight
        total_detections += weight
        magnitude_counts[
            bin_index(float(row["trailedSourceMag"]), config.dataset.magnitude_bins)
        ] += weight
        distance_counts[
            bin_index(float(row["Range_LTC_km"]) / AU_KM, config.dataset.distance_bins_au)
        ] += weight

    return _assemble(
        config,
        detected_weight * factor,
        total_detections * factor,
        [count * factor for count in magnitude_counts],
        [count * factor for count in distance_counts],
    )
