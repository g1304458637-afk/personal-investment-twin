"""Offline scripted choices read the actual exposed catalog, never tool results fake."""
import json


def input_payload(raw):
    if isinstance(raw, list):
        raw = raw[0]["content"]
    # Only test INPUT decoding: the fixed format-retry instruction may follow it.
    return json.JSONDecoder().raw_decode(raw)[0]


def choose_options(*kinds, facts=(), history=(), change=None):
    def respond(request):
        payload = input_payload(request["input"])
        catalog = payload["option_catalog"]
        choice = {
            "factual_option_ids": [o["option_id"] for o in catalog["factual_options"]
                                   if set(o["evidence_refs"]) & set(facts)],
            "historical_option_ids": [o["option_id"] for o in catalog["historical_options"]
                                      if set(o["evidence_refs"]) & set(history)],
            "claim_option_ids": [next(o["option_id"] for o in catalog["claim_options"] if o["claim_kind"] == kind)
                                 for kind in kinds],
            "question_kind": "need_contemporaneous_records",
        }
        if "answer_catalog" in payload:
            # Existing tests exercise motive legality, not new relevance choices.
            choice.update(answer_focus="decision_reason",
                          finding_option_ids=[o["option_id"] for o in payload["answer_catalog"][:1]])
        return json.dumps(change(choice, catalog) if change else choice)
    return respond
