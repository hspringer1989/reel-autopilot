"""Community automation: auto-replies to comments on our own posts, auto-replies
to DMs (with escalation of sensitive cases), and a daily engagement digest of
relevant foreign posts/profiles to engage with manually.

Every external call sits behind a port with an offline fake (`CommunityAPI` in
`api.py`), like the rest of the project. All Claude calls go through the existing
budget-gated `LLMProvider`; sensitive content is never auto-answered.
"""
