import json


def predict_tickets(tickets, config):
    from google import genai
    from google.genai import types
    client = genai.Client()

    prompt = f"""
You are a customer support triage assistant.

Classify ALL tickets using the configuration provided.

For every ticket, return:
- ticket_id
- category
- priority
- reason
- suggested_reply

Rules:
1. Category MUST be from allowed_categories.
2. Priority MUST be from allowed_priorities.
3. Follow reply_style tone and max_words.
4. Determine priority based on customer urgency.
5. Do not invent information or promise refunds.
6. Return JSON only, in this format:
{{"predictions": [{{"ticket_id": "...",
"category": "...", "priority": "...",
"reason": "...", "suggested_reply": "..."}}]}}

CONFIGURATION:
{json.dumps(config)}

NORMALIZED TICKETS:
{json.dumps(tickets)}
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0
        )
    )

    data = json.loads(response.text)
    raw_predictions = data["predictions"]

    allowed_categories = config["allowed_categories"]
    allowed_priorities = config["allowed_priorities"]
    routes = config["routing_rules"]
    max_words = config["reply_style"]["max_words"]

    # Fallback values must come from configuration
    fallback_category = (
        "other" if "other" in allowed_categories
        else allowed_categories[0]
    )
    fallback_priority = (
        "normal" if "normal" in allowed_priorities
        else allowed_priorities[0]
    )

    predictions_by_id = {
        str(p["ticket_id"]): p
        for p in raw_predictions
        if isinstance(p, dict) and "ticket_id" in p
    }

    predictions = []

    for ticket in tickets:
        tid = ticket["ticket_id"]
        p = predictions_by_id.get(tid, {})

        category = p.get("category")
        priority = p.get("priority")

        if category not in allowed_categories or category not in routes:
            category = fallback_category

        if priority not in allowed_priorities:
            priority = fallback_priority

        reply = str(p.get("suggested_reply") or
                    "Thank you for contacting support. We will review your request.")

        # Enforce maximum reply length
        reply = " ".join(reply.split()[:max_words])

        predictions.append({
            "ticket_id": tid,
            "category": category,
            "priority": priority,
            "reason": str(p.get("reason") or "Requires review"),
            "suggested_reply": reply,
            "route_to": routes[category]
        })

    return predictions
