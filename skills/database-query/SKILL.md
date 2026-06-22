---
name: database-query
description: Query this project's structured MySQL business data. Use when the user asks about concrete internal records, entities, products, inventory, prices, specifications, status, descriptions, sales records, or other database-backed business information.
---

# Database Query

Use this skill when the answer should come from structured internal database records.

## Workflow

1. List tables first.
   - Always call `list_sql_tables` before writing SQL.
   - Do not guess table names such as `products` or `records`.

2. Preview relevant tables.
   - Use `get_table_data` to inspect likely tables and real field names.
   - Common business tables may include inventory, sales, orders, products, or records, but confirm them at runtime.

3. Query only after confirming schema.
   - Use `execute_sql_query` for specific filtering, joins, or aggregation.
   - Prefer `SELECT` queries.
   - Use fuzzy matching for names when appropriate, adjusted to the actual field names.

4. Answer from the database result.
   - If records are found, summarize the actual returned data.
   - If no records are found, say that the database has no matching record.
   - Only then suggest public web search as a fallback.

## Guardrails

- Never invent table names or fields.
- Never answer concrete internal-data questions from general knowledge before checking the database.
- If a SQL error names a missing table, recover by listing tables again and using real table names.
