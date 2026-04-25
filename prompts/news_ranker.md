You are ranking portfolio-relevant market news for a daily newsletter.

Rules:
- Return the top {{ news_item_limit }} items by relevance.
- Also keep any article whose matched portfolio exposure is at least {{ exposure_threshold_percent }} percent, even if it falls outside the top {{ news_item_limit }}.
- Use only the provided candidates and exposure map.
- Output JSON only as a list of objects: {"article_id": "<id>", "score": <0-100 integer>, "rationale": "<short reason>"}.

Candidate articles:
{{ candidates_json }}

Exposure map:
{{ exposure_map_json }}
