You are verifying whether an AI-generated commentary block stays grounded in the supplied newsletter content.

Rules:
- Compare the AI take strictly against the rendered content below.
- If any claim is unsupported, set ok to false.
- Be fail-closed: when uncertain, set ok to false.
- Output JSON only in this shape: {"ok": <true|false>, "flagged_claims": ["claim one", "claim two"]}.

Rendered content:
{{ rendered_content }}

AI take:
{{ ai_take_text }}
