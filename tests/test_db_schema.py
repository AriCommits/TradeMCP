import pytest
import sqlite3
import os
from src.trading.db.schema import create_schemas

def test_create_schemas():
    db_path = "test_trading.db"
    
    # ensure it doesn't exist
    if os.path.exists(db_path):
        os.remove(db_path)
        
    create_schemas(db_path)
    
    assert os.path.exists(db_path)
    
    # check tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    expected_tables = [
        "model_registry", 
        "research_runs", 
        "model_evaluations",
        "execution_batches",
        "orders",
        "audit_log"
    ]
    
    for table in expected_tables:
        assert table in tables
        
    conn.close()
    
    # clean up
    os.remove(db_path)
