# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user: Bruce, a Chinese English learner preparing IELTS speaking answers and building a
personal corpus. He uses the PC to choose questions, write his real thoughts, manage generation,
and review content; he uses the Android wrapper while walking or commuting to listen repeatedly.

Open-source users run the same local workflow with their own StepFun or Fish key and corpus.
Bruce remains the first user, but a fresh user must be able to understand and complete the core
loop without learning the project's internal track or script terminology.

## Product Purpose

Turn the user's own ideas into natural native-English audio that is pleasant enough to replay and
clear enough to imitate. Success means the user can choose an IELTS question, answer freely in
Chinese or English, receive a faithful lightly edited native-English rendition, and repeatedly
listen to it like an ordinary podcast clip.

The audio remains immediately playable. A learner may then enter a guided study session: record
an initial answer, reconstruct every English sentence from its Chinese meaning, read saved
explanations, answer again with the complete Chinese meaning, then answer with only the question.
The app keeps recordings and difficult sentences for later review. It must not claim a verified
IELTS or pronunciation score when it has not measured one.

## Positioning

Unlike general podcasts, TV dialogue, or IELTS model answers, every clip is built from the user's
own meaning and anchored to a specific question. The durable advantage is personally relevant,
native-like input that contains expressions the user actually wants to say.

## Operating Context

The core loop is: choose an IELTS or daily-life question → answer freely → use Agent mode or the
optional StepFun API mode to produce natural English and a hidden performance script → generate
audio with StepAudio 2.5 TTS (Fish remains a fallback) → replay, imitate, download, or import it
into Android. Text files under `data/` remain the common interface for both modes.

The same web frontend runs against the local FastAPI server on PC and against imported corpus packs
inside a Capacitor Android shell. Bruce is involved at perceptual gates: voice choice, listening
acceptance, visual direction, and milestone acceptance.

## Capabilities and Constraints

- Python 3.11, FastAPI, native JavaScript, no frontend build step, no CDN, no framework.
- Local-first and zero-server; external calls use the user's own StepFun/Fish credentials.
- Agent mode is the default and has no text-API cost; optional API mode uses StepFun JSON output.
- Questioner and answerer are independent roles with user-selected gender and voice.
- Existing alignment, word highlighting, sentence seeking, bilingual display, server/pack data
  sources, exports, and Android packaging must remain functional.
- The planned study content needs a meaning-preserving Chinese sentence for each English sentence,
  a saved explanation, audio linkage, and error analysis only when the learner's original input
  provides evidence. Current generation still supports only its existing three-text contract.
- `data/` is product data and must remain human-readable, Agent-editable, atomic, and compatible.
- Real TTS consumes quota and runs only when explicitly requested or initiated by the user.

## Brand Commitments

The next desktop visual direction is a warm, quiet reading room: warm paper, brown ink and muted
olive actions. The design contract and complete reference screens are in `DESIGN.md` and
`docs/design/study-room-v2/`. The earlier blue-white screens remain historical references.

## Evidence on Hand

- More than one hundred real Bruce corpus items, plus public examples and an IELTS question bank.
- Working PC and Android flows, real Fish-generated samples, word-level alignment, and Playwright
  coverage.
- Existing icon assets and product name are functional rather than binding identity assets.
- No testimonials, commercial claims, or external brand photography may be invented.

## Product Principles

1. The user's meaning becomes a playable audio answer without waiting for study materials.
2. Naturalness must remain faithful and imitable; raw messiness and polished model-answer prose are
   both failures.
3. Content and transcript are the interface; decoration must yield to reading, listening, and
   selection.
4. Keep each learning step clear enough that the learner can finish the entire answer and later
   compare independent attempts.
5. Preserve local ownership, user-controlled API spend, and backwards-compatible product data.

## Accessibility & Inclusion

English transcripts require comfortable reading size and line height, visible keyboard focus,
selectable text, reduced-motion support, WCAG AA contrast, and touch targets suitable for the
Android wrapper. Chinese remains available as an optional reference layer rather than competing
with the English listening text.
