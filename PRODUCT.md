# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user: Bruce, a Chinese English learner preparing IELTS speaking answers and building a
personal corpus. He uses the PC to choose questions, write his real thoughts, manage generation,
and review content; he uses the Android wrapper while walking or commuting to listen repeatedly.

Open-source users may run the same local workflow with their own Fish Audio key and corpus, but
Bruce's daily learning loop remains the product's first priority.

## Product Purpose

Turn the user's own ideas into natural native-English audio that is pleasant enough to replay and
clear enough to imitate. Success means the user can choose an IELTS question, answer freely in
Chinese or English, receive a faithful lightly edited native-English rendition, and repeatedly
listen to it like an ordinary podcast clip.

The product is not a professional podcast studio or a software-directed learning system. It does
not need scoring, spaced repetition, pronunciation grading, or maximum broadcast production.

## Positioning

Unlike general podcasts, TV dialogue, or IELTS model answers, every clip is built from the user's
own meaning and anchored to a specific question. The durable advantage is personally relevant,
native-like input that contains expressions the user actually wants to say.

## Operating Context

The core loop is: choose an IELTS question → answer freely → use an Agent conversation to produce
natural English and a Fish-ready script → generate audio with Fish S2.1 Pro Free → replay, imitate,
and shadow it. Text files under `data/` are the interface between the app and Agent sessions.

The same web frontend runs against the local FastAPI server on PC and against imported corpus packs
inside a Capacitor Android shell. Bruce is involved at perceptual gates: voice choice, listening
acceptance, visual direction, and milestone acceptance.

## Capabilities and Constraints

- Python 3.11, FastAPI, native JavaScript, no frontend build step, no CDN, no framework.
- Local-first and zero-server; Fish Audio `s2.1-pro-free` is the only external generation service.
- No LLM API integration; rewriting stays in Agent conversations and plain-text files.
- Female interviewer and male answer voice; the answer voice must be easy for Bruce to imitate.
- Existing alignment, word highlighting, sentence seeking, bilingual display, server/pack data
  sources, exports, and Android packaging must remain functional.
- `data/` is product data and must remain human-readable, Agent-editable, atomic, and compatible.
- Real TTS consumes quota and runs only when explicitly requested or initiated by the user.

## Brand Commitments

The product should feel like a private editorial listening desk: calm, intelligent, useful, and
personal. It must not imitate Spotify, look like an admin dashboard, or present itself as a flashy
AI product. The selected visual direction is "安静编辑部"; the build workflow is comp-first.

## Evidence on Hand

- More than one hundred real Bruce corpus items, plus public examples and an IELTS question bank.
- Working PC and Android flows, real Fish-generated samples, word-level alignment, and Playwright
  coverage.
- Existing icon assets and product name are functional rather than binding identity assets.
- No testimonials, commercial claims, or external brand photography may be invented.

## Product Principles

1. The user's meaning becomes audio before derivative teaching content or new features.
2. Naturalness must remain faithful and imitable; raw messiness and polished model-answer prose are
   both failures.
3. Content and transcript are the interface; decoration must yield to reading, listening, and
   selection.
4. Prefer the smallest implementation that makes the user more willing to listen repeatedly.
5. Preserve local ownership, zero extra API cost, and backwards-compatible product data.

## Accessibility & Inclusion

English transcripts require comfortable reading size and line height, visible keyboard focus,
selectable text, reduced-motion support, WCAG AA contrast, and touch targets suitable for the
Android wrapper. Chinese remains available as an optional reference layer rather than competing
with the English listening text.
