"""The objective-validation ("assay") layer — benchmark a topology's OUTCOME against an external
benchmark, distinct from the runtime's intrinsic validation (conformance / replay / observation,
which prove the wiring runs, not that a topology beats a baseline).

Working name "assay" (a test of worth); the package name is provisional pending the vocabulary
session (docs/benchmarking/benchmarking-design-round1.md §8.4). Sprint 2 ships the Oracle taxonomy; later sprints
add the control-ran conformance check and the control plane (Suite / Arm / Trial / Report).

Application-layer: this package imports the public surface (substrate.api) and the model seam
(substrate.reference), never kernel internals — like topologies/.
"""

from .conformance import FAIL, NO_CONTROL, PASS, ControlRanCheck, check_control_ran
from .oracle import (
    EXTERNAL_GRADER,
    LOG_PROJECTION,
    ExternalGraderOracle,
    LogProjectionOracle,
    Oracle,
    Result,
)
from .report import ArmReport, Report, build_report, exact_mcnemar_p
from .run import CaseResult, UsageTotals, run_arm_on_case, run_suite
from .suite import (
    ABLATION,
    BASELINE,
    FULL,
    PLACEBO,
    Arm,
    Case,
    Suite,
    Topology,
)

__all__ = [
    # oracle (Sprint 2)
    "Result",
    "Oracle",
    "LogProjectionOracle",
    "ExternalGraderOracle",
    "LOG_PROJECTION",
    "EXTERNAL_GRADER",
    # suite inputs (Sprint 4)
    "Case",
    "Arm",
    "Suite",
    "Topology",
    "FULL",
    "ABLATION",
    "BASELINE",
    "PLACEBO",
    # control plane (Sprint 4)
    "CaseResult",
    "UsageTotals",
    "run_arm_on_case",
    "run_suite",
    # conformance guard (Sprint 3)
    "ControlRanCheck",
    "check_control_ran",
    "PASS",
    "FAIL",
    "NO_CONTROL",
    # report (Sprint 4)
    "Report",
    "ArmReport",
    "build_report",
    "exact_mcnemar_p",
]
