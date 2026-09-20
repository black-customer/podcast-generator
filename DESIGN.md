# DESIGN — IELTS Pod v1

## Direction

The approved world is a **personal language recording studio**: crisp, quiet, and task-led. The
interface should make a learner feel that one real answer is moving through a simple studio rail —
**Choose → Answer → Listen** — without exposing prompts, provider jargon, or internal tracks.

The ten approved reference comps live in `docs/design/v1/`. They define hierarchy and density, not
literal final copy. Screen 03 is revised to share one answer editor between **Agent mode** (default,
copy a complete task and wait) and **API mode** (one click, automatic rewrite and audio). Android
screen 10 ships only file import and manual LAN address in v1; QR and auto-discovery are deferred.

## Visual system

- Canvas `#F7F9FC`, surface `#FFFFFF`, ink `#0B1736`, muted text `#63708A`.
- Primary cobalt `#1267F3`; success mint `#19B77A`; coral only for destructive/error attention.
- System sans fonts only. English questions carry the strongest weight; Chinese is supporting text.
- Thin slate rules, compact 10–14px radii, restrained shadows, no gradients or glassmorphism.
- The signature is a precise cobalt waveform paired with the three-stage generation rail.
- No album covers, vinyl, decorative hero art, dashboard statistics, or low-opacity unread text.

## Navigation and surfaces

- Desktop: 开始练习 / 我的语料 / 正在播放 / 设置.
- Android: 题库 / 语料 / 正在播放 / 导入; settings is reached from the top-right control.
- Full mobile playback hides bottom navigation and never stacks a mini player beneath itself.
- Public surfaces use the concepts 雅思口语 and 日常表达. Monologue, podcast, track, episode, and
  performance-script language stays out of the ordinary UI.

## Content hierarchy

- `original_answer`: the learner's untouched input, available as a secondary reference.
- `natural_english`: the clean answer for reading, memorising, and sentence highlighting.
- `podcast_text`: the clean question-and-answer transcript shown by the player.
- `podcast_script`: internal TTS direction; never rendered in ordinary product UI.

## Interaction floor

- One primary action per state; controls keep the same wording through loading, success, and error.
- All text remains selectable. Keyboard focus is visible, touch targets are at least 44px, motion
  respects `prefers-reduced-motion`, and text/background pairs meet WCAG AA.
- Empty and failure states always explain the next action. API failure never silently switches mode.
- Server and pack data sources share the same reading/player components; generation is unavailable
  in offline pack mode rather than simulated.
