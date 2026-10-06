# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Confirmed Brand and Audience

On 2026-10-06 Bruce named the product **英语说说说** and confirmed that it serves Chinese
English learners. The purpose is an English speaking learning tool, with IELTS speaking as a
core scenario and everyday expression / voice-chat reuse as complementary scenarios.
Chinese is the interface and brand language; English remains the learning material language.
The name directly expresses repeated speaking. There is no separate English brand name.
System display names use this Chinese name; in-app pages use functional titles without brand banners.

## Users

Primary user: Bruce, a Chinese English learner preparing IELTS speaking answers and building a
personal corpus. Android is also a primary learning surface: he imports voice-chat transcripts,
uses his own StepFun API to prepare materials, listens and practises oral recall on the go.
PC remains available for management and Agent processing; daily mobile learning needs no PC server.

Open-source users run the same local workflow with their own StepFun or Fish key and corpus.
Bruce remains the first user, but a fresh user must be able to understand and complete the core
loop without learning the project's internal track or script terminology.

## Product Purpose

Help Chinese learners speak English more often using their own meanings. A learner can choose an
IELTS question or reuse an English conversation, receive faithful natural-English audio that is
pleasant to replay and clear to imitate, then practise reconstructing and independently speaking
the expression. Generating an audio clip is a foundation for the learning loop, not the complete
product outcome; listening remains freely available without mandatory study.

The audio remains immediately playable. A learner may then enter a guided study session: record
an initial answer, reconstruct every English sentence from its Chinese meaning, read saved
explanations, answer again with the complete Chinese meaning, then answer with only the question.
The app keeps recordings and difficult sentences for later review. It must not claim a verified
IELTS or pronunciation score when it has not measured one.

## Positioning

Materials are built from the learner's own meaning and anchored to an IELTS question or an actual
conversation source. The learning loop connects natural input, retrieval, recordings and review to
repeated independent speaking. The durable advantage is personally relevant native-like expression
that the user wants to say and can practise with their own attempts.

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
- Study content includes a meaning-preserving Chinese sentence for each English sentence,
  a saved explanation, audio linkage, and error analysis only when the learner's original input
  provides evidence. Audio generation keeps its three-text contract; study material is submitted
  separately after audio completion.
- `data/` is product data and must remain human-readable, Agent-editable, atomic, and compatible.
- Real TTS consumes quota and runs only when explicitly requested or initiated by the user.

## Brand Commitments

The Chinese name **英语说说说** is confirmed. Bruce retained the existing app icon and rejected
the new icon candidates and the large blue home banner. Keep all original icon resources unchanged.
Home directly offers Chinese-to-English oral practice, answer reveal and existing answer audio.
Home practice never marks study complete or updates a review schedule; formal learning stays separate.

Bruce approved both the R3 light porcelain / cobalt palette and the dark midnight / ice-blue palette,
with a one-tap theme switch. Their final tokens and screenshots are in the U01 implementation handoff.
The final mobile behavior and implementation evidence are at `docs/design/mobile-implementation-u01/`.
The R4 icon candidates and banner are discarded history rather than implementation references.

The next desktop visual direction is a warm, quiet reading room: warm paper, brown ink and muted
olive actions. The design contract and complete reference screens are in `DESIGN.md` and
`docs/design/study-room-v2/`. The earlier blue-white screens remain historical references.

## Evidence on Hand

- More than one hundred real Bruce corpus items, plus public examples and an IELTS question bank.
- Working PC and Android flows, real Fish-generated samples, word-level alignment, and Playwright
  coverage.
- The Chinese system display name and original icon assets are binding; in-app branding is removed.
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
