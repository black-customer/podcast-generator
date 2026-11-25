"""从英文示范文本推断可选的美式语流提示。"""
import re

WORDS = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*|\d+(?:\.\d+)?")
WEAK = {"a": "ə", "an": "ən", "the": "ðə", "and": "ən", "to": "tə", "of": "əv",
        "for": "fər", "that": "ðət", "can": "kən", "was": "wəz", "were": "wər",
        "at": "ət", "as": "əz", "from": "frəm", "than": "ðən", "some": "səm"}
FUNCTION = frozenset(
    "i me my you your he she it we they us them his her their this these those do does did "
    "is am are have has had will would could should may might must in on with or if be been".split()
)
REDUCTIONS = {("going", "to"), ("want", "to"), ("kind", "of"), ("sort", "of"),
              ("did", "you"), ("would", "you"), ("could", "you")}
WH_QUESTION = {"who", "what", "where", "when", "why", "which", "how", "whose", "whom"}
FLAP = re.compile(r"[aeiou]t{1,2}(?:er|le|y|ing|ed)(?:s)?$")


def annotate_sentence(text: str) -> dict:
    matches = list(WORDS.finditer(text))
    words = [match[0].lower().replace("’", "'") for match in matches]
    focus = [i for i, word in enumerate(words) if word not in WEAK and word not in FUNCTION]
    weak = {str(i): "ði" if word == "the" and words[i + 1][0] in "aeiou" else WEAK[word]
            for i, word in enumerate(words[:-1]) if word in WEAK}
    pairs, breaks = [], []
    group_start = 0
    for i, (left, right) in enumerate(zip(words[:-1], words[1:], strict=True)):
        gap = text[matches[i].end():matches[i + 1].start()]
        if (re.search(r"[,;:—–.!?]", gap) or
                (i - group_start >= 4 and right in {"but", "because", "although", "when"})):
            breaks.append(i)
            group_start = i + 1
            continue
        kind = None
        if (left, right) in REDUCTIONS:
            kind = "reduction"
        elif right[0] in "aeiou" and re.search(r"[aeiour][td]$", left):
            kind = "flap_t"
        elif right[0] in "aeiou" and re.search(r"[bcdfghjklmnpqrstvwxyz]$", left):
            kind = "cv_link"
        elif left.endswith(("t", "d", "p", "b", "k", "g")) and right[0] in "pbtdkgmnfvs":
            kind = "held_stop"
        if kind:
            pairs.append({"from": i, "to": i + 1, "type": kind})
    if not focus and words:
        focus = [len(words) - 1]
    rising = text.rstrip(' ”’"').endswith("?") and bool(words and words[0] not in WH_QUESTION)
    return {"words": [match[0] for match in matches], "focus_words": focus,
            "nuclear_word": focus[-1] if focus else None, "weak_words": weak,
            "linking_pairs": pairs, "flap_t_words": [i for i, word in enumerate(words)
                                                    if FLAP.search(word)],
            "break_after": breaks, "intonation": "↗" if rising else "↘"}
