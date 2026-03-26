use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct Order {
    order_id: usize,
    symbol: String,
    side: String,
    size: f64,
    expected_edge_bps: f64,
    forecast_vol: f64,
    pofi: f64,
}

#[derive(Debug, Deserialize)]
struct Request {
    orders: Vec<Order>,
    max_shortfall_bps: f64,
}

#[derive(Debug, Serialize)]
struct Decision {
    order_id: usize,
    symbol: String,
    approve: bool,
    predicted_shortfall_bps: f64,
    reason: String,
    adjusted_size: f64,
}

#[derive(Debug, Serialize)]
struct Response {
    decisions: Vec<Decision>,
}

fn predict_shortfall_bps(size: f64, forecast_vol: f64, pofi: f64, side: &str) -> f64 {
    let side_impact = if side == "BUY" { 1.05 } else { 1.0 };
    let base_spread = 4.0;
    let size_term = 120.0 * size.abs() * forecast_vol.max(0.0001);
    let pofi_term = 16.0 * pofi.abs();
    (base_spread + size_term + pofi_term) * side_impact
}

fn evaluate(req: Request) -> Response {
    let mut decisions = Vec::with_capacity(req.orders.len());

    for order in req.orders {
        let shortfall = predict_shortfall_bps(order.size, order.forecast_vol, order.pofi, &order.side);
        let approve_by_edge = shortfall <= order.expected_edge_bps;
        let approve_by_cap = shortfall <= req.max_shortfall_bps;
        let approve = approve_by_edge && approve_by_cap;

        let reason = if approve {
            "ok".to_string()
        } else if shortfall > order.expected_edge_bps {
            "predicted_shortfall_exceeds_expected_edge".to_string()
        } else {
            "predicted_shortfall_exceeds_max_shortfall".to_string()
        };

        decisions.push(Decision {
            order_id: order.order_id,
            symbol: order.symbol,
            approve,
            predicted_shortfall_bps: shortfall,
            reason,
            adjusted_size: if approve { order.size } else { 0.0 },
        });
    }

    Response { decisions }
}

fn main() {
    let mut input = String::new();
    if io::stdin().read_to_string(&mut input).is_err() {
        eprintln!("failed to read stdin");
        std::process::exit(1);
    }

    let req: Request = match serde_json::from_str(&input) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("invalid request json: {}", e);
            std::process::exit(1);
        }
    };

    let resp = evaluate(req);

    match serde_json::to_string(&resp) {
        Ok(json) => println!("{}", json),
        Err(e) => {
            eprintln!("failed to serialize response: {}", e);
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_if_shortfall_above_edge() {
        let req = Request {
            orders: vec![Order {
                order_id: 0,
                symbol: "ABC".to_string(),
                side: "BUY".to_string(),
                size: 0.5,
                expected_edge_bps: 5.0,
                forecast_vol: 0.04,
                pofi: 0.2,
            }],
            max_shortfall_bps: 50.0,
        };

        let resp = evaluate(req);
        assert_eq!(resp.decisions.len(), 1);
        assert!(!resp.decisions[0].approve);
        assert_eq!(resp.decisions[0].adjusted_size, 0.0);
    }

    #[test]
    fn approves_when_cost_is_bounded() {
        let req = Request {
            orders: vec![Order {
                order_id: 0,
                symbol: "XYZ".to_string(),
                side: "SELL".to_string(),
                size: 0.02,
                expected_edge_bps: 25.0,
                forecast_vol: 0.01,
                pofi: 0.01,
            }],
            max_shortfall_bps: 30.0,
        };

        let resp = evaluate(req);
        assert_eq!(resp.decisions.len(), 1);
        assert!(resp.decisions[0].approve);
        assert!(resp.decisions[0].adjusted_size > 0.0);
    }
}
