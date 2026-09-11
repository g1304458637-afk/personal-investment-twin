"""Stage failure enum extracted from upstream protocols.py; see LICENSE."""
from enum import Enum

class StageFailureReason(str, Enum):
    STAGE_FAILURE = "stage_failure"
    TIMEOUT = "timeout"
    BUDGET_SKIP = "budget_skip"
