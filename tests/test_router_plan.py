import pytest
import os
from src.trading.router import ModelRouter, JobType

def test_router_cloud():
    router = ModelRouter()
    assert router.route_job(JobType.PLANNING) == ModelRouter.CLOUD_MODEL
    assert router.route_job(JobType.ORCHESTRATION) == ModelRouter.CLOUD_MODEL

def test_router_local():
    os.environ["LOCAL_MODEL_ENDPOINT"] = "test-local-model"
    router = ModelRouter()
    assert router.route_job(JobType.EXECUTION) == "test-local-model"
    assert router.route_job(JobType.MONITORING) == "test-local-model"
    
    # clean up
    del os.environ["LOCAL_MODEL_ENDPOINT"]
