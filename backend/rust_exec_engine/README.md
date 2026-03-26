Rust execution backend for predicted slippage and implementation shortfall checks.

Build:

cargo build --release

Run manually with JSON stdin:

echo '{"orders":[{"order_id":0,"symbol":"AAPL","side":"BUY","size":0.05,"expected_edge_bps":20.0,"forecast_vol":0.02,"pofi":0.01}],"max_shortfall_bps":35.0}' | ./target/release/rust_exec_engine
