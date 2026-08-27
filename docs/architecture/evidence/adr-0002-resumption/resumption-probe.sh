#!/usr/bin/env bash
# Resumption probe — the protocol behind ADR-0002's resumption table.
#
# ADR-0001 cited a resumption that happened by accident: an external SIGTERM killed a
# 20,416-job run at 96 % and it resumed without recomputing. One observation at one point
# of progress proves nothing about the general case, so this turns it into a measurement.
#
# What it does, in order:
#
#   1. A baseline run that is never interrupted, hashed artifact by artifact.
#   2. A determinism control — a second clean run — because comparing a resumed run against
#      a baseline says nothing until you know two clean runs agree. They do not, by design;
#      see the note on seeds below.
#   3. A kill at each target percentage in two regimes, resumed and compared.
#
# **SIGKILL to the process group, not SIGTERM to snakemake.** SIGTERM gives the
# orchestrator the chance to shut down in order and release its lock, which is the gentle
# case. The hard case — a power loss, an OOM kill — is the one that can leave a truncated
# artifact behind, so it is the one worth probing. Both are run, because they behave
# differently and the difference is the finding.
#
# **On artifact comparison.** The campaign stage draws its seed from the operating system
# and records it, mirroring the real simulator, whose authors warn that a fixed seed
# "should never be used for science results" (see simulators/base.py). Detections and
# everything downstream therefore differ between any two runs, interrupted or not. What
# must hold is that the *deterministic* artifacts — those whose seeds derive from
# master_seed — come back byte-identical, and that a resumed run differs from the baseline
# no more than two clean runs differ from each other.
#
# Usage:
#     docs/architecture/evidence/adr-0002-resumption/resumption-probe.sh [experiment.toml]
#
# Defaults to a copy of the smoke experiment redirected to its own output tree, so it
# never competes with a real run for runs/smoke-fake.

set -u

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT" || exit 1

SOURCE_CONFIG=${1:-experiments/smoke-fake.toml}
CONFIG=experiments/.resumption-probe.toml
OUT=runs/resumption-probe
WORK=$(mktemp -d)
TARGETS=${TARGETS:-"15 30 50 95"}
CORES=${CORES:-4}

trap 'rm -f "$CONFIG"; rm -rf "$WORK"' EXIT

sed "s|^outdir = .*|outdir = \"$OUT\"|" "$SOURCE_CONFIG" > "$CONFIG"

snake() {
    setsid uv run snakemake --cores "$CORES" --resources bench_slot=1 \
        --config experiment="$CONFIG" "$@"
}

# Deterministic artifacts only: manifests carry wall-clock and timestamps, and the
# detections tables are stochastic by design.
hash_deterministic() {
    find "$OUT" -type f \( -name 'orbits.csv' -o -name 'physical-parameters.csv' \
        -o -name 'theta.json' -o -name 'draws.txt' \) 2>/dev/null | sort \
        | while read -r f; do
            printf '%s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "${f#"$OUT"/}"
        done
}

hash_all() {
    find "$OUT" -type f ! -name '*.manifest.json' ! -name 'measurements.json' 2>/dev/null \
        | sort | while read -r f; do
            printf '%s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "${f#"$OUT"/}"
        done
}

progress() {
    grep -oE '\([0-9]+%\) done' "$1" 2>/dev/null | tail -1 | grep -oE '[0-9]+'
}

jobs_executed() {
    sed -n '/Job stats:/,/^total/p' "$1" | grep -E '^total' | tail -1 | awk '{print $2}'
}

run_to_completion() {
    snake "${@:2}" > "$1" 2>&1 &
    local pid=$!
    wait "$pid"
    return $?
}

# ---------------------------------------------------------------- baseline and control
echo "=== baseline: a run that is never interrupted ==="
rm -rf "$OUT" .snakemake
run_to_completion "$WORK/baseline.log"
baseline_rc=$?
echo "rc=$baseline_rc  jobs=$(jobs_executed "$WORK/baseline.log")"
hash_deterministic > "$WORK/baseline.deterministic"
hash_all > "$WORK/baseline.all"
echo "deterministic artifacts: $(wc -l < "$WORK/baseline.deterministic")"

echo ""
echo "=== determinism control: a second clean run ==="
rm -rf "$OUT" .snakemake
run_to_completion "$WORK/control.log"
hash_deterministic > "$WORK/control.deterministic"
hash_all > "$WORK/control.all"
if diff -q "$WORK/baseline.deterministic" "$WORK/control.deterministic" > /dev/null; then
    echo "deterministic artifacts: identical across two clean runs"
else
    echo "deterministic artifacts: DIFFER across two clean runs — investigate before"
    echo "reading anything below, the comparison is meaningless until this holds"
fi
echo "stochastic drift between two clean runs: \
$(diff "$WORK/baseline.all" "$WORK/control.all" | grep -cE '^[<>]') lines \
(expected: the campaign stage draws its seed from the OS)"

# ------------------------------------------------------------------------------ kills
for regime in sigterm sigkill; do
    for target in $TARGETS; do
        [ "$regime" = sigterm ] && [ "$target" != 30 ] && continue

        echo ""
        echo "=== $regime at ~${target}% ==="
        rm -rf "$OUT" .snakemake

        # Launched inline rather than through snake(), and the reason is worth keeping:
        # calling a shell function in the background makes $! the PID of the *subshell*,
        # which belongs to this script's own process group. Killing that group kills the
        # script — and whatever invoked it. Launching setsid directly makes $! the leader
        # of the new group, which is the only group this loop is allowed to signal.
        setsid uv run snakemake --cores "$CORES" --resources bench_slot=1 \
            --config experiment="$CONFIG" > "$WORK/kill.log" 2>&1 &
        pid=$!
        sleep 0.3
        pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
        own_pgid=$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')
        if [ -z "${pgid:-}" ] || [ "$pgid" = "$own_pgid" ]; then
            echo "refusing to signal process group '${pgid:-unset}': it is this script's own"
            kill -TERM "$pid" 2>/dev/null
            continue
        fi

        killed=0
        for _ in $(seq 1 4000); do
            pct=$(progress "$WORK/kill.log")
            if [ -n "${pct:-}" ] && [ "$pct" -ge "$target" ]; then
                if [ "$regime" = sigterm ]; then
                    kill -TERM "$pid"
                else
                    kill -9 -"$pgid"
                fi
                echo "killed at ${pct}% of the DAG"
                killed=1
                break
            fi
            kill -0 "$pid" 2>/dev/null || { echo "run finished before ${target}%"; break; }
            sleep 0.05
        done
        wait "$pid" 2>/dev/null
        [ "$killed" = 0 ] && continue

        echo "files on disk after the kill: $(find "$OUT" -type f 2>/dev/null | wc -l)"

        # Resume without unlocking first: whether this succeeds is the finding.
        if run_to_completion "$WORK/resume.log" --rerun-incomplete; then
            echo "resumed unaided: rc=0"
        else
            if grep -q LockException "$WORK/resume.log"; then
                echo "resumption REFUSED — stale lock left by the kill"
                snake --unlock > "$WORK/unlock.log" 2>&1
                echo "  snakemake --unlock -> rc=$?"
                run_to_completion "$WORK/resume.log" --rerun-incomplete
                echo "  resumed after unlock: rc=$?"
            else
                echo "resumption failed for another reason — see the log"
                tail -5 "$WORK/resume.log"
                continue
            fi
        fi

        echo "jobs re-executed by the resumption: $(jobs_executed "$WORK/resume.log")"

        hash_deterministic > "$WORK/resumed.deterministic"
        if diff -q "$WORK/baseline.deterministic" "$WORK/resumed.deterministic" > /dev/null; then
            echo "deterministic artifacts: identical to the baseline \
($(wc -l < "$WORK/resumed.deterministic") files)"
        else
            echo "deterministic artifacts: DIFFER from the baseline — \
$(diff "$WORK/baseline.deterministic" "$WORK/resumed.deterministic" | grep -cE '^[<>]') lines"
        fi
    done
done

rm -rf "$OUT" .snakemake
echo ""
echo "=== done ==="
