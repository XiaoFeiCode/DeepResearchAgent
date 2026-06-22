---
name: web-research
description: Search public internet information for this project. Use when the user asks for external public knowledge, background research, current information, or fallback information after internal database or RAGFlow sources cannot answer.
---

# Web Research

Use this skill only for public information.

## When To Search

Use web search when:

- the question is about public background knowledge
- the user asks for current or external information
- internal database lookup has no matching record
- RAGFlow has no relevant assistant or knowledge-base answer

Do not use web search first for:

- concrete internal record, product, price, inventory, specification, status, or sales-record questions
- legal or specialized knowledge-base questions that should go to RAGFlow first
- uploaded-file questions that should use file-reading tools first

## Search Pattern

1. Start with a broad query.
2. Add one or two narrower queries if the first result is incomplete.
3. Stop when enough evidence is collected.
4. Return the useful findings to the main agent for synthesis.
5. Preserve each source title, URL, and summary content. Do not strip URLs.

## Source Links

- When the final answer uses web search, include a "来源链接" section.
- Each source should include the original URL from `sources` or `source_urls`.
- If a search result has no URL, say the source link is missing instead of inventing one.
- Keep public web information separate from internal database or RAGFlow information.

## Guardrails

- Do not exceed five searches for one user request unless the user explicitly asks for deep research.
- Keep search queries specific and avoid repeating the same query.
- Clearly separate public web information from internal database or RAGFlow information.
