---
name: document-generation
description: Generate Markdown or PDF documents in this project after required information has been gathered. Use when the user explicitly asks to create reports, guides, summaries, Markdown files, PDF files, or other written output files.
---

# Document Generation

Use this skill when the user explicitly asks for a generated file.

## Required Order

1. Gather information first.
   - Use the appropriate subagent or file-reading tool before generating a document.
   - Do not call `generate_markdown` with placeholder text such as "waiting for search results".

2. Create Markdown first.
   - Use `generate_markdown` for Markdown output.
   - If the user asks for PDF, first generate Markdown, then call `convert_md_to_pdf`.

3. Save only in the current session workspace.
   - Follow the runtime workspace instruction injected by the server.
   - Use relative paths under the provided session directory.

4. Report completion without exposing paths.
   - Tell the user the document was created.
   - Do not send local file paths in the chat response unless the system explicitly requires it.

## Content Rules

- Include a todo list for complex document tasks.
- Base the document on retrieved information, uploaded files, database results, or RAGFlow results.
- Do not generate file types the user did not request.
- For substantial reports, write complete content rather than a short note.
