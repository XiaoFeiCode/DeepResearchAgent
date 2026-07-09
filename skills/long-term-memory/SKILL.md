---
name: long-term-memory
description: Recall or save durable user-specific knowledge across conversations. Use for stable preferences, reusable rules, proven strategies, templates, or important historical conclusions; never use for secrets or transient chat details.
---

# Long-Term Memory

Use Milvus long-term memory only for information that remains useful in future conversations.

## Recall

1. Search long-term memory when a task may depend on prior user preferences, reusable rules, previous strategies, templates, or historical conclusions.
2. Treat recalled memories as context, not unquestionable truth.
3. Prefer the current user request when it conflicts with an older memory.

## Save

Save a memory when the user explicitly asks to remember something, or when the information is clearly stable and reusable:

- `preference`: stable user preferences
- `rule`: durable business or review rules
- `strategy`: a proven reusable approach
- `template`: a reusable output or workflow template
- `conclusion`: an important reviewed historical conclusion

## Guardrails

- Never save passwords, API keys, access tokens, private credentials, or sensitive personal data.
- Never save temporary task status, raw tool output, or the full conversation.
- Keep each memory concise and independently understandable.
- Do not save guesses or unverified claims.
