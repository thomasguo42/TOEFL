# Reading Seeds

This directory now houses curated JSON fixtures that act as deterministic fallbacks whenever real-time Gemini generation is unavailable:

- `reading_sentences.json` – annotated complex sentences for the Sentence Gym exercises. Each entry already encodes highlight segments, Simplified Chinese tooltips, and a reference paraphrase so the backend can deliver deterministic feedback if Gemini is offline.
- `reading_paragraphs.json` – paragraph-level practice data for the Paragraph Lab. Sentences are tagged with their rhetorical roles, and transition markers include localized explanations to support the Logical Flow Mapper overlay.
- `reading_passages.json` – guided passage scenarios for the Strategy Simulator. Content includes paragraph summaries, scaffold toggles, and question metadata (correct answers plus distractor categories) so we can provide rationale-rich coaching when AI calls fail.

Keep these files version controlled. Whenever you expand coverage (e.g., add new topics or difficulty bands), document the change here so instructors understand what scenarios students will encounter.
