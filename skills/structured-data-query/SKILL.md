---
name: structured-data-query
description: Route concrete internal record questions to the structured database first. Use when the user asks about a named entity, product, item, price, inventory, specification, status, description, or business record that may exist in the project's database.
---

# Structured Data Query

Use this skill to route concrete internal-data questions correctly.

## Routing Rules

1. For a concrete entity, item, product, record, order, inventory, price, specification, status, description, or other business-data question, use the database first.
   - Examples: "数据库里有没有某个条目", "这个商品多少钱", "库存还有多少", "规格是什么", "查一下某个记录".
   - Use the `database-query` workflow.

2. If the database returns matching records, answer only from those records.
   - Include fields that are actually present in the query result.
   - Do not add unsupported claims from general knowledge.

3. If the database has no matching record, clearly say that no internal record was found.
   - Then the main agent may use RAGFlow or web research as a fallback if the user question still needs an answer.

4. If the question is about uploaded files, manuals, contracts, policies, or knowledge-base documents, use file reading or RAGFlow before web search.

## Common Failure To Avoid

Do not answer a concrete internal-data question by immediately using internet search. The database is the first source for project-owned structured records.
