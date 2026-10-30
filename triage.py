"""Historical logistics triage replay. Offline mode uses only Python's standard library."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import random
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from triage_types import Proposal

ROOT = Path(__file__).resolve().parent
REQUIRED = {
    "Order Id", "Order Item Id", "Order Item Total", "Days for shipping (real)",
    "Days for shipment (scheduled)", "Delivery Status", "Order Status", "Shipping Mode",
}
TERMINAL = {"CANCELED", "SUSPECTED_FRAUD"}
STATUSES = {"COMPLETE", "PENDING", "CLOSED", "PENDING_PAYMENT", "CANCELED",
            "PROCESSING", "SUSPECTED_FRAUD", "ON_HOLD", "PAYMENT_REVIEW"}
DELIVERY_STATUSES = {"Advance shipping", "Late delivery", "Shipping on time", "Shipping canceled"}


@dataclass(frozen=True)
class Policy:
    version: str = "1.0"
    max_auto_delay_days: int = 1
    max_auto_value: float = 500.0  # Dataset monetary units; currency is not verified.
    min_evidence_completeness: float = 1.0
    min_proposal_confidence: float = 0.90


@dataclass(frozen=True)
class Order:
    order_id: str
    actual_days: Optional[float]
    scheduled_days: Optional[float]
    value: Optional[float]
    delivery_status: str
    order_status: str
    shipping_mode: str
    item_count: int
    issues: tuple[str, ...] = ()

    @property
    def delay_days(self):
        if self.actual_days is None or self.scheduled_days is None:
            return None
        return max(0.0, self.actual_days - self.scheduled_days)

    @property
    def evidence_completeness(self):
        fields = [self.actual_days is not None, self.scheduled_days is not None,
                  self.value is not None, bool(self.delivery_status),
                  bool(self.order_status), bool(self.shipping_mode)]
        return sum(fields) / len(fields)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def load_orders(path):
    """Read only an explicit allowlist. Customer fields are never retained."""
    groups = {}
    rows = 0
    missing_ids = 0
    with Path(path).open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing columns: " + ", ".join(sorted(REQUIRED - set(reader.fieldnames or []))))
        for row in reader:
            rows += 1
            safe = {k: (row.get(k) or "").strip() for k in REQUIRED}
            if not safe["Order Id"]:
                missing_ids += 1
                # Never combine unrelated rows with missing order IDs.
                safe["Order Id"] = f"missing-id-row-{rows}"
                safe["_missing_id"] = True
            groups.setdefault(safe["Order Id"], []).append(safe)
    orders = []
    for order_id, items in groups.items():
        first = items[0]
        issues = []
        if first.get("_missing_id"):
            issues.append("missing_order_id")
        for key in ("Days for shipping (real)", "Days for shipment (scheduled)",
                    "Delivery Status", "Order Status", "Shipping Mode"):
            if len({r[key] for r in items}) > 1:
                issues.append("conflicting_" + key)
        item_ids = [r["Order Item Id"] for r in items]
        if any(not i for i in item_ids) or len(set(item_ids)) != len(item_ids):
            issues.append("missing_or_duplicate_item_id")
        totals = [number(r["Order Item Total"]) for r in items]
        total = round(sum(totals), 2) if all(t is not None for t in totals) else None
        orders.append(Order(order_id, number(first["Days for shipping (real)"]),
                            number(first["Days for shipment (scheduled)"]), total,
                            first["Delivery Status"], first["Order Status"],
                            first["Shipping Mode"], len(items), tuple(issues)))
    return orders, {"source_rows": rows, "unique_orders": len(orders), "missing_order_id_rows": missing_ids}


def permitted_action(order, policy):
    """Deterministic authority boundary: an LLM cannot override this function."""
    if order.issues:
        return "ESCALATE", "Conflicting or invalid source records: " + ", ".join(order.issues)
    if order.evidence_completeness < policy.min_evidence_completeness:
        return "ESCALATE", "Required evidence is incomplete."
    if order.order_status not in STATUSES or order.delivery_status not in DELIVERY_STATUSES:
        return "ESCALATE", "Unrecognised source status."
    if (order.order_status in TERMINAL) != (order.delivery_status == "Shipping canceled"):
        return "ESCALATE", "Order and delivery cancellation evidence conflicts."
    if order.order_status in TERMINAL:
        return "ESCALATE", "Canceled or fraud-flagged order requires specialist review."
    if order.delay_days is None or order.value is None:
        return "ESCALATE", "Timing or order value is unavailable."
    expected = "Late delivery" if order.delay_days > 0 else (
        "Shipping on time" if order.actual_days == order.scheduled_days else "Advance shipping")
    if order.delivery_status != expected:
        return "ESCALATE", "Timing and delivery label conflict."
    if order.delay_days == 0:
        return "NO_ACTION", "No historical delay recorded."
    if order.order_status in {"ON_HOLD", "PAYMENT_REVIEW", "PENDING_PAYMENT"}:
        return "ESCALATE", "Payment or hold status requires human review."
    if order.delay_days > policy.max_auto_delay_days:
        return "ESCALATE", "Delay exceeds the permitted automatic-action limit."
    if order.value > policy.max_auto_value:
        return "ESCALATE", "Order value exceeds the permitted automatic-action limit."
    return "MONITOR", "Minor delay with complete evidence and value within policy."


def simulated_proposal(order, policy):
    action, rationale = permitted_action(order, policy)
    # 1.0 denotes deterministic agreement, NOT probability of a correct business decision.
    return Proposal(action, 1.0, "OFFLINE SIMULATION: " + rationale)


def decide(order, proposal, policy, mode="offline", error=None):
    allowed, reason = permitted_action(order, policy)
    final = allowed
    valid_proposal = (isinstance(proposal, Proposal) and proposal.action in {"MONITOR", "ESCALATE", "NO_ACTION"}
                      and isinstance(proposal.confidence, (float, int))
                      and not isinstance(proposal.confidence, bool)
                      and math.isfinite(proposal.confidence) and 0 <= proposal.confidence <= 1)
    if error is not None:
        final, reason = "ESCALATE", "Agent failed; human review required."
    elif not valid_proposal:
        final, reason = "ESCALATE", "Invalid agent proposal."
    elif allowed == "ESCALATE":
        final = "ESCALATE"
    elif proposal.confidence < policy.min_proposal_confidence:
        final, reason = "ESCALATE", "Proposal confidence below configured threshold (uncalibrated)."
    elif proposal.action == "ESCALATE":
        final, reason = "ESCALATE", "Agent requested human review."
    elif proposal.action != allowed:
        final, reason = "ESCALATE", "Agent recommendation conflicts with permitted action."
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "replay_type": "retrospective_outcome_replay",
        "mode": mode, "policy": asdict(policy), "evidence": asdict(order),
        "delay_days": order.delay_days, "evidence_completeness": order.evidence_completeness,
        "proposal": asdict(proposal) if valid_proposal else None,
        "agent_error_type": error, "permitted_action": allowed,
        "final_action": final, "reason": reason,
        "simulation_only": True,
    }


def execute_simulation(decision):
    """Return a local queue event. There are no external side effects."""
    return {
        "order_id": decision["evidence"]["order_id"],
        "timestamp_utc": decision["timestamp_utc"],
        "run_id": decision.get("run_id"),
        "queue": {"MONITOR": "simulated_monitoring", "ESCALATE": "human_review",
                  "NO_ACTION": "no_action"}[decision["final_action"]],
        "reason": decision["reason"], "simulated": True,
    }


def write_report(path, summary, decisions):
    # Show a balanced selection; the JSONL audit contains every processed decision.
    examples = []
    for action in ("MONITOR", "ESCALATE", "NO_ACTION"):
        examples.extend([d for d in decisions if d["final_action"] == action][:40])
    body = []
    for d in examples:
        o = d["evidence"]
        body.append('<tr data-action="{action}"><td>{id}</td><td><span class="pill {action}">{label}</span></td>'
                    '<td>{delay}</td><td>{value}</td><td>{reason}</td></tr>'.format(
                        action=d["final_action"], id=html.escape(o["order_id"]),
                        label={"MONITOR": "Monitor", "ESCALATE": "Human review", "NO_ACTION": "No action"}[d["final_action"]],
                        delay="Unknown" if d["delay_days"] is None else f'{d["delay_days"]:g} days',
                        value="Unknown" if o["value"] is None else f'{o["value"]:,.2f}',
                        reason=html.escape(d["reason"])))
    counts = summary["decisions"]
    cards = "".join(f'<div class="card"><strong>{counts.get(k, 0):,}</strong><span>{label}</span></div>'
                    for k, label in [("MONITOR", "Simulated monitoring"), ("ESCALATE", "Human review"), ("NO_ACTION", "No action")])
    template = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Logistics triage · Replay report</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f3ef;color:#172d39;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:auto;padding:48px 32px}header{display:flex;justify-content:space-between;gap:24px;align-items:start}h1{font-size:44px;letter-spacing:-1.8px;line-height:1.12;margin:12px 0 20px}h2{font-size:23px;margin-bottom:8px}.eyebrow{font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#53736c}.badge{background:#e3ece8;color:#295b50;border:1px solid #c3d5ce;padding:8px 14px;border-radius:30px;font-size:13px;white-space:nowrap}.intro{max-width:730px;color:#53616b}.notice{border-left:4px solid #b87c2c;background:#fff8e9;padding:16px 20px;margin:28px 0;color:#655137}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:white;border:1px solid #dedfd8;border-radius:14px;padding:22px}.card strong{display:block;font-size:36px;letter-spacing:-1px}.card span{color:#5e6d76;font-size:14px}.flow{padding:24px;background:#193d43;color:#eef5ef;border-radius:14px;margin:24px 0}.flow small{display:block;color:#bdd5ce;margin-top:8px}select,input{font:inherit;padding:9px 12px;border-radius:7px;border:1px solid #bdc9c8;background:#fff;color:#193d43;margin:8px 10px 16px 0}table{width:100%;border-collapse:collapse;background:white}th{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.8px;color:#63747a;background:#e9eeea}td,th{padding:14px;border-bottom:1px solid #e8eae4;vertical-align:top}td{font-size:13px}td:last-child{max-width:390px}.pill{display:inline-block;border-radius:20px;padding:3px 10px;white-space:nowrap;font-weight:600}.MONITOR{background:#dfefe5;color:#245c3f}.ESCALATE{background:#fae8cd;color:#805214}.NO_ACTION{background:#edf0f2;color:#52626e}.scroll{overflow-x:auto;border:1px solid #dedfd8;border-radius:12px}footer{font-size:13px;color:#66757c;margin-top:28px}.meta{font-size:14px;color:#63747a}.links a{color:#295b50}@media(max-width:700px){main{padding:28px 16px}header{display:block}h1{font-size:35px}.cards{grid-template-columns:1fr}.badge{display:inline-block}.flow{font-size:14px}}
</style></head><body><main><header><div><div class="eyebrow">Bounded autonomy / Logistics</div><h1>Every decision.<br>A clear boundary.</h1></div><div class="badge">__MODE__ · Historical replay</div></header>
<p class="intro">A delivery-delay triage prototype that routes minor deviations to simulated monitoring and uncertain or higher-impact cases to a human. Rules control the final action; every decision is recorded.</p>
<div class="notice"><strong>Research prototype.</strong> Uses recorded historical outcomes, not live tracking or advance predictions. All actions are simulated. Offline mode makes no AI calls; its confidence value denotes deterministic agreement and is not a probability.</div>
<p class="meta">__ROWS__ source rows · __ORDERS__ distinct orders · __PROCESSED__ orders processed in this run</p>
<section class="cards">__CARDS__</section><div class="flow">Read order → Gather evidence → Propose action → Enforce policy → Log outcome<small>Auto-monitor: delay ≤ __DELAY__ day(s), value ≤ __VALUE__ dataset units, complete consistent evidence, eligible status, proposal confidence ≥ __CONFIDENCE__. Thresholds are illustrative.</small></div>
<h2>Inspect the decisions</h2><p class="meta">Up to 40 examples per action. Full results are in decisions.jsonl; simulated queues are in queues.jsonl.</p>
<label for="action">Action </label><select id="action"><option value="">All actions</option><option value="MONITOR">Monitor</option><option value="ESCALATE">Human review</option><option value="NO_ACTION">No action</option></select><label for="search">Find </label><input id="search" placeholder="Order ID or reason">
<div class="scroll"><table><thead><tr><th>Order</th><th>Decision</th><th>Delay</th><th>Value / dataset units</th><th>Reason</th></tr></thead><tbody>__BODY__</tbody></table></div>
<footer><p>Confidence is uncalibrated. Counts describe policy routing, not prediction accuracy, cost savings, or proven operational value. The dataset does not establish material criticality, production impact, or a verified currency.</p><p>Data: Constante, Silva &amp; Pereira (2019), <a href="https://doi.org/10.17632/8gx2fvg2k6.3">DataCo SMART SUPPLY CHAIN FOR BIG DATA ANALYSIS, v3</a>, CC BY 4.0. Records aggregated to order level; customer fields excluded.</p><p>Run __RUN__ · Policy __POLICY__ · __TIME__</p></footer></main>
<script>const action=document.querySelector('#action'),search=document.querySelector('#search');function filter(){document.querySelectorAll('tbody tr').forEach(row=>{row.hidden=!!((action.value&&row.dataset.action!==action.value)||!row.textContent.toLowerCase().includes(search.value.toLowerCase()))})}action.addEventListener('change',filter);search.addEventListener('input',filter);</script></body></html>'''
    substitutions = {"MODE": summary["mode"].upper(), "ROWS": f'{summary["source_rows"]:,}',
                     "ORDERS": f'{summary["unique_orders"]:,}', "PROCESSED": f'{summary["processed_orders"]:,}',
                     "CARDS": cards, "BODY": "".join(body), "RUN": summary["run_id"],
                     "POLICY": summary["policy"]["version"], "TIME": summary["timestamp_utc"],
                     "DELAY": str(summary["policy"]["max_auto_delay_days"]),
                     "VALUE": f'{summary["policy"]["max_auto_value"]:g}',
                     "CONFIDENCE": str(summary["policy"]["min_proposal_confidence"])}
    for key, value in substitutions.items():
        template = template.replace("__" + key + "__", value)
    path.write_text(template, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "examples" / "synthetic_orders.csv")
    parser.add_argument("--mode", choices=["offline", "openai"], default="offline")
    parser.add_argument("--limit", type=int, default=200, help="Orders to replay; 0 means all (offline only).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-auto-value", type=float, default=500.0)
    parser.add_argument("--max-auto-delay", type=int, default=1)
    parser.add_argument("--min-confidence", type=float, default=0.90)
    parser.add_argument("--output", type=Path, default=ROOT / "runs")
    args = parser.parse_args()
    if args.limit < 0 or args.max_auto_delay < 0 or not math.isfinite(args.max_auto_value) or args.max_auto_value < 0:
        parser.error("Limits, value and delay must be nonnegative and finite.")
    if not 0 <= args.min_confidence <= 1:
        parser.error("Confidence threshold must be between 0 and 1.")
    if args.mode == "openai" and (args.limit == 0 or args.limit > 20):
        parser.error("Live mode is capped at 20 orders per run. Use --limit 5 to start.")
    policy = replace(Policy(), max_auto_value=args.max_auto_value,
                     max_auto_delay_days=args.max_auto_delay, min_proposal_confidence=args.min_confidence)
    proposer = simulated_proposal
    if args.mode == "openai":
        from sdk_agent import make_proposer
        proposer = make_proposer()
    orders, profile = load_orders(args.csv)
    random.Random(args.seed).shuffle(orders)
    selected = orders[:args.limit] if args.limit else orders
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = args.output / run_id
    output.mkdir(parents=True, exist_ok=False)
    decisions = []
    with (output / "decisions.jsonl").open("w", encoding="utf-8") as log, (output / "queues.jsonl").open("w", encoding="utf-8") as queues:
        for order in selected:
            try:
                proposal = proposer(order, policy)
                decision = decide(order, proposal, policy, args.mode)
            except Exception as exc:
                # Do not write exception messages, which could contain request details or secrets.
                decision = decide(order, None, policy, args.mode, type(exc).__name__)
            decision["run_id"] = run_id
            log.write(json.dumps(decision, allow_nan=False) + "\n")
            queues.write(json.dumps(execute_simulation(decision), allow_nan=False) + "\n")
            decisions.append(decision)
    summary = {
        **profile, "run_id": run_id, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
        "processed_orders": len(selected), "sampling": "seeded shuffle of distinct orders", "seed": args.seed,
        "mode": args.mode, "policy": asdict(policy),
        "decisions": dict(Counter(d["final_action"] for d in decisions)),
        "agent_failures": sum(d["agent_error_type"] is not None for d in decisions),
        "simulation_only": True, "retrospective": True,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_report(output / "report.html", summary, decisions)
    print(json.dumps(summary, indent=2))
    print("\nOpen report:", output / "report.html")


if __name__ == "__main__":
    main()
