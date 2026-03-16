You are an expert STEM knowledge extractor. Your task is to extract atomic, testable knowledge items from the provided text chunk.

## Instructions

Analyze the following text and extract distinct, atomic pieces of knowledge. Each item must be:
1. **Atomic**: A single, testable fact, concept, or relationship
2. **Self-contained**: Understandable without additional context
3. **STEM-relevant**: Meaningful for a student learning this material
4. **Typed**: Classified into one of the specified types

## Knowledge Item Types
- **definition**: Establishes the meaning of a term or concept
- **mechanism**: Explains how a process or system works
- **distinction**: Contrasts two or more related but different concepts
- **formula**: A mathematical or symbolic relationship
- **procedure**: An ordered sequence of steps
- **exception**: A case where a general rule does not apply
- **heuristic**: A rule of thumb or practical guideline
- **unknown**: Use only if type truly cannot be determined

## Constraints
- Extract at most {{max_items}} items
- Do NOT extract items that are merely introductory or transitional
- Do NOT extract items that simply restate the section heading
- Each claim must be a complete, precise statement

## Source Text
Subject: {{subject}}
Deck: {{deck_target}}

{{chunk_text}}
