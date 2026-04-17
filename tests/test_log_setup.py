import pytest
import json
import logging
from io import StringIO
from src.trading.log_setup import setup_logging

def test_json_logging():
    from io import StringIO
    
    stream = StringIO()
    logger = setup_logging(level=logging.INFO, stream=stream)
    
    logger.info("Test message")
    
    log_output = stream.getvalue().strip()
    
    log_dict = json.loads(log_output)
    
    assert log_dict["level"] == "INFO"
    assert log_dict["message"] == "Test message"
    assert "timestamp" in log_dict
