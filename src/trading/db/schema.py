import sqlite3
import os

def create_schemas(db_path: str = "trading.db"):
    """
    Two Logical Data Stores: Research DB and Execution DB.
    We are implementing them as tables in SQLite for simplicity here,
    but they represent distinct domains.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- RESEARCH DB TABLES ---
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS model_registry (
        model_id TEXT PRIMARY KEY,
        model_type TEXT NOT NULL,
        hyperparameters JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        asset_class_tags TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS research_runs (
        run_id TEXT PRIMARY KEY,
        model_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        start_date TEXT,
        end_date TEXT,
        confidence_score REAL,
        rank INTEGER,
        FOREIGN KEY (model_id) REFERENCES model_registry(model_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS model_evaluations (
        eval_id TEXT PRIMARY KEY,
        model_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        metric_value REAL NOT NULL,
        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (model_id) REFERENCES model_registry(model_id)
    )
    """)

    # --- EXECUTION DB TABLES ---
    # Joined to Research DB by (model_id, execution_batch_id)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS execution_batches (
        batch_id TEXT PRIMARY KEY,
        model_id TEXT NOT NULL,
        asset_profile_id TEXT NOT NULL,
        execution_window_start TIMESTAMP,
        execution_window_end TIMESTAMP,
        status TEXT NOT NULL,
        FOREIGN KEY (model_id) REFERENCES model_registry(model_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        order_config JSON NOT NULL,
        order_result JSON,
        state TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (batch_id) REFERENCES execution_batches(batch_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        log_id TEXT PRIMARY KEY,
        batch_id TEXT,
        order_id TEXT,
        event_type TEXT NOT NULL,
        payload JSON NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (batch_id) REFERENCES execution_batches(batch_id),
        FOREIGN KEY (order_id) REFERENCES orders(order_id)
    )
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_schemas()
