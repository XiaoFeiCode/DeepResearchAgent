---
name: image-retrieval
description: Search the user's multimodal image knowledge base with text, an uploaded image, or both. Use when the user asks for similar images, matching products, related screenshots, visual cases, or image examples.
---

# Image Retrieval

Use `search_image_knowledge` when the requested output includes images from the private image knowledge base.

## Routing

1. Text-to-image search:
   - Put the user's visual description in `query_text`.
   - Leave `image_path` empty.

2. Image-to-image search:
   - Pass the uploaded image path in `image_path`.
   - Use `query_text` only when the user wants to emphasize a feature.

3. Image understanding is different from retrieval:
   - Use `analyze_image` when the user asks what an image contains.
   - Use `search_image_knowledge` when the user asks to find matching or similar images.
   - Use both when the task needs visual interpretation and retrieval.

4. Result handling:
   - Mention the number of matches and the most relevant items.
   - Put each result's `display_token` immediately after the paragraph that discusses that image, so the frontend can render it inline.
   - Distribute image references across the answer instead of collecting them at the end.
   - Do not invent images when no match passes the similarity threshold.
   - Do not expose storage paths or replace `display_token` with a raw URL.
