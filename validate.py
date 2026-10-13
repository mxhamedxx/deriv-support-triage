"""Check that all files and post-review results agree with disk inputs and config."""
import json
from pathlib import Path

STAGES = [
    "INIT", "INPUTS_LOADED", "TICKETS_NORMALIZED", "TRIAGE_PREDICTED",
    "HUMAN_REVIEW_COMPLETE", "FINAL_QUEUE_GENERATED",
    "VALIDATION_COMPLETE", "RESULTS_FINALISED"
]


def validate_outputs(base=None, expect_complete=True):
    base = Path(base) if base else Path(__file__).resolve().parent

    def load(name):
        path = base / name
        assert path.is_file(), f"Missing artifact: {name}"
        return json.loads(path.read_text(encoding="utf-8"))

    tickets = load("tickets.json")
    cfg = load("triage_config.json")
    norm = load("normalized_tickets.json")
    preds = load("triage_predictions.json")
    overrides = load("review_overrides.json")
    queue = load("final_queue.json")
    stages = load("pipeline_states.json")
    assert (base / "queue_summary.md").is_file(), "Missing queue_summary.md"
    assert stages == STAGES[:len(stages)], "Incorrect pipeline stage order"
    assert stages == (STAGES if expect_complete else STAGES[:6]), "Pipeline stage missing"
    allowed_c = cfg["allowed_categories"]
    allowed_p = cfg["allowed_priorities"]
    routes = cfg["routing_rules"]
    max_words = cfg["reply_style"]["max_words"]
    ids = [str(t["ticket_id"]) for t in tickets]
    assert len(ids) == len(set(ids)), "Duplicate input IDs"
    assert len(norm) == len(tickets), "Normalization count mismatch"
    assert [n["ticket_id"] for n in norm] == ids, "Normalization ticket IDs/order mismatch"
    for original, n in zip(tickets, norm):
        subject = str(original.get("subject") or "").strip()
        message = str(original.get("message") or "").strip()
        expected = f"Subject: {subject}\nMessage: {message}"
        assert n["text_for_model"] == expected, "Incorrect deterministic normalization"
        assert n["char_count"] == len(expected), "Incorrect character count"
        assert n["subject"] == subject and n["message"] == message, "Incorrect normalized fields"
        assert n["channel"] == str(original.get("channel") or ""), "Incorrect channel"
        assert n["created_at"] == str(original.get("created_at") or ""), "Incorrect timestamp"
    assert len(preds) == len(ids), "Prediction count mismatch"
    assert len({p["ticket_id"] for p in preds}) == len(ids), "Duplicate prediction IDs"
    assert {p["ticket_id"] for p in preds} == set(ids), "Missing/extra predictions"
    pred_by_id = {p["ticket_id"]: p for p in preds}
    for p in preds:
        assert p["category"] in allowed_c, "Invalid predicted category"
        assert p["priority"] in allowed_p, "Invalid predicted priority"
        assert p["route_to"] == routes[p["category"]], "Incorrect predicted route"
        assert isinstance(p["reason"], str), "Missing reason"
        assert len(p["suggested_reply"].split()) <= max_words, "Predicted reply too long"
    override_map = {}
    for o in overrides:
        tid = o["ticket_id"]
        assert tid in pred_by_id and tid not in override_map, "Invalid/duplicate override ID"
        old = pred_by_id[tid]
        assert o["old_category"] == old["category"] and o["old_priority"] == old["priority"], "Incorrect previous values"
        assert o["new_category"] in allowed_c and o["new_priority"] in allowed_p, "Invalid override values"
        assert (o["new_category"], o["new_priority"]) != (o["old_category"], o["old_priority"]), "No-op override logged"
        override_map[tid] = o
    assert len(queue) == len(ids), "Final count mismatch"
    assert [q["ticket_id"] for q in queue] == ids, "Final IDs/order mismatch"
    for q in queue:
        tid = q["ticket_id"]
        p = pred_by_id[tid]
        o = override_map.get(tid)
        category = o["new_category"] if o else p["category"]
        priority = o["new_priority"] if o else p["priority"]
        assert q["final_category"] == category, "Override not applied to category"
        assert q["final_priority"] == priority, "Override not applied to priority"
        assert q["final_route_to"] == routes[category], "Final routing not recomputed"
        assert q["was_overridden"] is (o is not None), "Incorrect override flag"
        assert q["suggested_reply"] == p["suggested_reply"], "Suggested reply mismatch"
        assert len(q["suggested_reply"].split()) <= max_words, "Final reply too long"
    summary = (base / "queue_summary.md").read_text(encoding="utf-8")
    assert f"Total tickets: {len(queue)}" in summary, "Summary count is wrong"
    print("VALIDATION PASSED:", len(queue), "tickets,", len(overrides), "overrides")
    return True


if __name__ == "__main__":
    validate_outputs()
