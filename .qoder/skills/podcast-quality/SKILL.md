---
name: podcast-quality
description: Use for audio, corpus text, TTS, mastering, player, question-bank UI, or other user-facing quality changes in PodcastGenerate. Do not use for unrelated documentation-only chores.
---

# PodcastGenerate quality workflow

1. Read `docs/CONSTITUTION.md`, `docs/ROADMAP.md`, `docs/PROGRESS.md`, and
   `docs/QUALITY_PLAYBOOK.md` before changing files.
2. Identify the relevant playbook section and inspect the current implementation and tests.
3. State a plan of at most five bullets. Prefer the smallest change that advances the product's
   core loop: choose a question, express an answer, hear a natural native-English version.
4. For bugs and data changes, add a failing regression test first. Preserve unrelated user edits.
5. Run the relevant focused tests while working, then `bash scripts/check.sh` before completion.
6. Report concrete evidence. UI changes need desktop/mobile screenshots; perceptual audio changes
   need Bruce's listening gate and must never trigger live TTS without explicit approval.
