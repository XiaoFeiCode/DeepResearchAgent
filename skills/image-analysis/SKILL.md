---
name: image-analysis
description: Analyze user-uploaded PNG, JPEG, or WebP images with the vision model. Use for screenshots, photographed documents, charts, interfaces, objects, equipment panels, and visible fault symptoms.
---

# Image Analysis

Use this skill when the user's task depends on visual information in an uploaded image.

## Workflow

1. Identify the relevant uploaded image.
   - Use the exact file name shown in the current session workspace.
   - Do not use `read_file_content` for image files.

2. Call `analyze_image` before drawing conclusions.
   - Pass the image path and a question that reflects the user's real goal.
   - For screenshots, ask for visible text, interface state, and error details.
   - For equipment photos, ask for model numbers, warning indicators, fault codes, and visible damage.
   - For charts, ask for axes, legends, trends, anomalies, and important values.

3. Treat the visual result as evidence, not certainty.
   - Distinguish clearly between visible facts and inferred conclusions.
   - If text is unclear or a region is blocked, state the limitation instead of guessing.

4. Continue with the appropriate information source when needed.
   - Use RAGFlow for matching private knowledge-base material.
   - Use the database assistant for structured internal records.
   - Use web research only when public or current information is required.

5. Keep safety boundaries.
   - Do not identify a real person or infer sensitive personal traits from an image.
   - For medical, legal, electrical, or mechanical risks, provide cautious guidance and recommend professional confirmation when appropriate.
