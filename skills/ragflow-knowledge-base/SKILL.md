---
name: ragflow-knowledge-base
description: Manage RAGFlow knowledge bases in this project. Use when the user wants to create a RAGFlow dataset, inspect knowledge base status, upload files, parse uploaded documents, delete documents, or prepare a knowledge base before asking RAGFlow assistants.
---

# RAGFlow Knowledge Base

Use this skill to handle RAGFlow knowledge-base operations as a workflow, not as isolated API calls.

## Decision Flow

1. If the user asks a domain question that should be answered from an existing RAGFlow assistant, use the RAGFlow assistant query flow:
   - Get assistant list.
   - Pick the assistant whose name or description best matches the question.
   - Ask that assistant.

2. If the user asks for actual images, charts, screenshots, or illustrations from a RAGFlow document:
   - Identify the target dataset and, when possible, the target document.
   - Use `search_ragflow_document_images` so the original parsed images are returned to the UI.
   - Do not replace the images with text-only descriptions or public web search results.
   - For an uploaded query image, call `analyze_image` first and use its OCR and visual description as the retrieval query.

3. If the user asks to manage knowledge-base content, use the knowledge-base management flow:
   - Inspect existing knowledge bases.
   - Create the target knowledge base if it does not exist.
   - Upload the provided files.
   - Parse uploaded documents unless the user explicitly says not to.
   - Inspect the target knowledge base again to confirm document status.

4. If RAGFlow has no relevant assistant or no relevant knowledge base content, report that clearly. Do not silently fall back to internet search unless the main task explicitly allows public web fallback.

## Preferred Tools

For a complete setup or upload workflow, prefer:

```text
setup_ragflow_knowledge_base
```

Use it when the request includes one or more of these actions:

- create a knowledge base
- upload one or more files
- upload and parse files
- prepare a knowledge base for later Q&A

For status checks, prefer:

```text
inspect_ragflow_knowledge_base
```

Use it when the user asks:

- what knowledge bases exist
- whether a document has been uploaded
- what files are in a knowledge base
- whether RAGFlow currently has data

Use the lower-level tools only when the user asks for one exact operation, such as only deleting a document or only listing documents.

## File Path Rules

When uploading files, pass paths exactly as project-relative or absolute paths. Project-relative paths are resolved from the project root.

Examples:

```text
ragflow/law.docx
updated/session_xxx/file.pdf
E:/Dev/Code/llm-agents/deep_agent_project/ragflow/law.docx
```

If a file is missing, report the missing path and ask the user to provide the correct path or upload the file.

## User-Facing Behavior

When the operation succeeds, summarize:

- knowledge base name
- whether it was created or reused
- uploaded document names
- parse status
- current document list

When RAGFlow is reachable but empty, say that it is connected but has no knowledge bases or assistants yet.

When RAGFlow is unreachable, report the connection or API error directly and do not pretend the upload happened.
