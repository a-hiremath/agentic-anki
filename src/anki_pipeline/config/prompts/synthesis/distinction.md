You are creating an Anki flashcard for a STEM distinction.

## Task
Convert the following knowledge item into a STEMCloze Anki card.

**Card design principles:**
- Use cloze deletions to test the distinguishing properties
- Format: "X has {{c1::property}} while Y has {{c2::property}}"
- Test the key distinguishing feature, not superficial differences
- BackExtra (optional): Worked example showing the distinction

## Knowledge Item
Type: distinction
Claim: {{claim}}
Subject: {{subject_tag_root}}
Evidence: {{evidence_text}}

## Requirements
- Must use {{c1::...}} syntax (at least one cloze)
- Each cloze should test a meaningful, non-trivial property
- The stem (non-cloze parts) must make the cloze unambiguous
- If mathematical notation is needed, use \(...\) for inline math and \[...\] for display math
- Never use $...$ or $$...$$ delimiters
