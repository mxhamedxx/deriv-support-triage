"""Replayable support triage pipeline: live Gemini by default, --offline for local dry runs."""
import argparse
import json
from collections import Counter
from pathlib import Path

from llm_service import predict_tickets

BASE = Path(__file__).resolve().parent
STAGES = [
    "INIT", "INPUTS_LOADED", "TICKETS_NORMALIZED", "TRIAGE_PREDICTED",
    "HUMAN_REVIEW_COMPLETE", "FINAL_QUEUE_GENERATED",
    "VALIDATION_COMPLETE", "RESULTS_FINALISED"
]


def read_json(filename):
    return json.loads((BASE / filename).read_text(encoding="utf-8"))


def save_json(filename, data):
    (BASE / filename).write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


class Workflow:
    def __init__(self):
        self.history = ["INIT"]
        save_json("pipeline_states.json", self.history)

    def advance(self, stage):
        expected = STAGES[len(self.history)]
        if stage != expected:
            raise RuntimeError(f"Invalid stage transition: expected {expected}, got {stage}")
        self.history.append(stage)
        save_json("pipeline_states.json", self.history)
        print("State:", stage)


def normalize_tickets(tickets):
    normalized = []
    for ticket in tickets:
        subject = str(ticket.get("subject") or "").strip()
        message = str(ticket.get("message") or "").strip()
        text = f"Subject: {subject}\nMessage: {message}"
        normalized.append({
            "ticket_id": str(ticket["ticket_id"]),
            "subject": subject,
            "message": message,
            "channel": str(ticket.get("channel") or ""),
            "created_at": str(ticket.get("created_at") or ""),
            "text_for_model": text,
            "char_count": len(text)
        })
    return normalized


def offline_demo_predict(tickets, config):
    """Local ONLY: deterministic test double, not an LLM or production triage."""
    keywords = {
        "billing_issue": ["charged", "charge", "deposit", "refund", "billing", "payment"],
        "account_access": ["password", "login", "log in", "access", "credentials"],
        "product_how_to": ["how do", "how can", "export", "download", "where can"],
        "bug_report": ["crash", "error", "bug", "broken", "closes", "fails"]
    }
    valid_categories = [c for c in config["allowed_categories"] if c in config["routing_rules"]]
    allowed_priorities = config["allowed_priorities"]
    fallback_cat = "other" if "other" in valid_categories else valid_categories[0]
    normal = "normal" if "normal" in allowed_priorities else allowed_priorities[0]
    predictions = []
    for ticket in tickets:
        content = ticket["text_for_model"].lower()
        scores = {
            category: sum(phrase in content for phrase in keywords.get(category, category.replace("_", " ").split()))
            for category in valid_categories if category != "other"
        }
        best = max(scores, key=scores.get) if scores else fallback_cat
        category = best if scores and scores[best] > 0 else fallback_cat
        urgent_terms = ("urgently", "urgent", "immediately", "asap", "before market open")
        priority = "urgent" if any(term in content for term in urgent_terms) and "urgent" in allowed_priorities else normal
        reply = "Thank you for contacting support. We have received your request and will review it."
        reply = " ".join(reply.split()[:config["reply_style"]["max_words"]])
        predictions.append({
            "ticket_id": ticket["ticket_id"], "category": category, "priority": priority,
            "reason": "Offline demo rule; replace with real LLM output for evaluation.",
            "suggested_reply": reply,
            "route_to": config["routing_rules"][category]
        })
    return predictions


def human_review(predictions, config):
    originals = {p["ticket_id"]: p for p in predictions}
    reviewed = {p["ticket_id"]: p.copy() for p in predictions}
    print("\nPREDICTIONS FOR HUMAN REVIEW")
    for p in predictions:
        print(f"{p['ticket_id']}: {p['category']} | {p['priority']}")
    print("\nEnter any overrides as: ticket_id,category,priority")
    print("Press Enter on an empty line when done.")
    while True:
        try:
            line = input("Override> ").strip()
        except EOFError:
            line = ""  # automated evaluation can close stdin to accept predictions
        if not line:
            break
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 3:
            print("Use: ticket_id,category,priority")
            continue
        tid, category, priority = parts
        if tid not in reviewed:
            print("Unknown ticket ID. Try again.")
            continue
        if category not in config["allowed_categories"] or category not in config["routing_rules"]:
            print("Invalid category. Allowed:", ", ".join(config["allowed_categories"]))
            continue
        if priority not in config["allowed_priorities"]:
            print("Invalid priority. Allowed:", ", ".join(config["allowed_priorities"]))
            continue
        reviewed[tid]["category"] = category
        reviewed[tid]["priority"] = priority
        reviewed[tid]["route_to"] = config["routing_rules"][category]
        print("Accepted:", tid)

    overrides = []
    for tid, final in reviewed.items():
        old = originals[tid]
        if (old["category"], old["priority"]) != (final["category"], final["priority"]):
            overrides.append({
                "ticket_id": tid,
                "old_category": old["category"], "new_category": final["category"],
                "old_priority": old["priority"], "new_priority": final["priority"]
            })
    return reviewed, overrides


def build_final_queue(tickets, reviewed, overrides, config):
    changed = {override["ticket_id"] for override in overrides}
    return [
        {
            "ticket_id": ticket["ticket_id"],
            "final_category": reviewed[ticket["ticket_id"]]["category"],
            "final_priority": reviewed[ticket["ticket_id"]]["priority"],
            "final_route_to": config["routing_rules"][reviewed[ticket["ticket_id"]]["category"]],
            "suggested_reply": reviewed[ticket["ticket_id"]]["suggested_reply"],
            "was_overridden": ticket["ticket_id"] in changed
        }
        for ticket in tickets
    ]


def write_summary(queue, overrides, config):
    categories = Counter(p["final_category"] for p in queue)
    priorities = Counter(p["final_priority"] for p in queue)
    destinations = Counter(p["final_route_to"] for p in queue)
    lines = ["# Agent Queue Summary", "", f"Total tickets: {len(queue)}", "", "## Final categories"]
    lines += [f"- {category}: {categories[category]}" for category in config["allowed_categories"]]
    lines += ["", "## Final priorities"]
    lines += [f"- {priority}: {priorities[priority]}" for priority in config["allowed_priorities"]]
    lines += ["", "## Destination queues"]
    lines += [f"- {route}: {destinations[route]}" for route in dict.fromkeys(config["routing_rules"].values())]
    lines += ["", "## Human overrides"]
    if overrides:
        for o in overrides:
            lines.append(f"- {o['ticket_id']}: {o['old_category']} / {o['old_priority']} -> {o['new_category']} / {o['new_priority']}")
    else:
        lines.append("- None")
    (BASE / "queue_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Demo test double only: no LLM call")
    args = parser.parse_args()
    workflow = Workflow()
    tickets, config = read_json("tickets.json"), read_json("triage_config.json")
    if not isinstance(tickets, list) or not config["allowed_categories"] or not config["allowed_priorities"]:
        raise ValueError("Invalid input ticket list or config")
    if any(c not in config["routing_rules"] for c in config["allowed_categories"]):
        raise ValueError("Every category needs a routing rule")
    ids = [str(t["ticket_id"]) for t in tickets]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate ticket IDs")
    workflow.advance("INPUTS_LOADED")
    normalized = normalize_tickets(tickets)
    save_json("normalized_tickets.json", normalized)
    workflow.advance("TICKETS_NORMALIZED")
    print(f"Normalized {len(normalized)} tickets")
    if args.offline:
        print("OFFLINE DEMO ONLY: these are not LLM predictions")
        predictions = offline_demo_predict(normalized, config)
    else:
        print("Calling Gemini once for all tickets...")
        predictions = predict_tickets(normalized, config)
    save_json("triage_predictions.json", predictions)
    workflow.advance("TRIAGE_PREDICTED")
    reviewed, overrides = human_review(predictions, config)
    save_json("review_overrides.json", overrides)
    workflow.advance("HUMAN_REVIEW_COMPLETE")
    final_queue = build_final_queue(normalized, reviewed, overrides, config)
    save_json("final_queue.json", final_queue)
    write_summary(final_queue, overrides, config)
    from dashboard import build_dashboard
    build_dashboard(final_queue, normalized, config)
    workflow.advance("FINAL_QUEUE_GENERATED")
    from validate import validate_outputs
    validate_outputs(BASE, expect_complete=False)
    workflow.advance("VALIDATION_COMPLETE")
    workflow.advance("RESULTS_FINALISED")
    print("SUCCESS: generated final_queue.json and queue_summary.md")


if __name__ == "__main__":
    main()
