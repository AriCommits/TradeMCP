import os
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class JobType(str, Enum):
    PLANNING = "planning"
    ORCHESTRATION = "orchestration"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    IMPLEMENTATION = "implementation"


class ModelRouter:
    """
    Two-tier model routing strategy.
    Planning and high-level orchestration -> high-capability model (Opus).
    Execution, monitoring, and low-level -> configurable local model.
    """

    CLOUD_MODEL = "claude-3-opus-20240229"

    def __init__(self):
        # Local model configurable via env variable
        self.local_model = os.environ.get("LOCAL_MODEL_ENDPOINT", "llama-3-8b-instruct")

    def route_job(self, job_type: JobType) -> str:
        """Returns the appropriate model endpoint (cloud vs. local)"""
        if job_type in (JobType.PLANNING, JobType.ORCHESTRATION):
            model = self.CLOUD_MODEL
        else:
            model = self.local_model
            
        logger.info(f"ModelRouter: Routed {job_type.value} task to model {model}")
        return model
