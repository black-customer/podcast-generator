"""单题诊断器：对一份雅思考生的口语回答做确定性量化。

纯规则，零网络调用，零模型调用——同一份输入永远得到同一份输出。
存在的理由：凭印象挑「最显眼」的三个错误，通常不是分数损失最大的三个。
这个脚本把「哪个错误出现几次、值多少分」变成数字，让 Agent 按数字排序挑。

用法：
    python diagnose.py --question "..." --answer "..."
    python diagnose.py --question "..." --answer-file my.txt --json out.json
"""
# ruff: noqa: E501  # HTML/CSS 模板与规则字符串是数据，折行会看不清

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

# ---------------------------------------------------------------- 规则包
# impact：1=听着不地道，2=明显 6 分特征，3=直接压分（考官会记为语法错误）
RULES: list[tuple[str, str, str, int, str]] = [
    # --- 语法化石
    ("g_uncount_s", "可数性",
     r"\b(knowledges|informations|advices|sceneries|softwares|feedbacks|progresses|jewelleries|researches|equipments)\b",
     3, "这批词永远不加 s"),
    ("g_a_uncount", "可数性",
     r"\b(a|an)\s+(knowledge|advice|information|feedback|progress|equipment|scenery)\b",
     3, "不可数名词不能直接接 a/an，要说 a piece of / a lot of"),
    ("g_too_much_pl", "量词", r"\btoo much\s+\w+s\b", 3, "复数可数名词用 too many"),
    ("g_very_comp", "比较级", r"\bvery\s+(worse|better|bigger|easier|harder|more)\b",
     3, "比较级前用 much / far，不用 very"),
    ("g_more_comp", "比较级", r"\bmore\s+(better|worse|easier|harder|bigger)\b", 2, "比较级不能叠加 more"),
    ("g_very_very", "强调", r"\bvery\s+very\b", 2, "写一次 very 就够了，或者换 really / incredibly"),
    ("g_uncount_have", "主谓一致",
     r"\b(technology|information|knowledge|equipment|advice|feedback|education|the economy)\s+have\b",
     3, "不可数主语配单数动词 has"),
    ("g_pl_has", "主谓一致", r"\b(these|those|many|several|lots|a lot)\s+(of\s+)?\w+s\s+has\b",
     3, "复数主语配 have"),
    ("g_every_pl", "主谓一致", r"\b(every|each)\s+\w+s\b", 2, "every / each 后面接单数名词"),
    ("g_have_base", "完成时",
     r"\b(have|has|haven't|hasn't|'ve)\s+(teach|do|sing|go|see|know|make|take|give|say|be|attach)\b",
     3, "have 后面必须是过去分词"),
    ("g_used_to_ing", "过去习惯", r"\bused to\s+\w+ing\b",
     3, "used to 加动词原形；be used to 加 doing 才是「习惯于」"),
    ("g_like_to_ing", "动词框架", r"\b(like|enjoy|prefer|love|hate)\s+to\s+\w+ing\b",
     2, "like to do 或 like doing，二选一，不能混"),
    ("g_suggest_obj", "动词框架",
     r"\b(suggest|recommend|advise|explain|describe|announce|share)\s+(everyone|everybody|people|him|her|them|me|us|someone|children|students|my)\s+to\s+\w+",
     3, "suggest / recommend 不接 sb to do；用 suggest that sb do 或 advise sb to do"),
    ("g_let_to", "使役", r"\b(let|make|have|help)\s+(me|him|her|us|them|you|someone)\s+to\s+\w+",
     3, "let / make / have 加人再加动词原形，不带 to"),
    ("g_motivate_ing", "动词框架",
     r"\b(motivate|encourage|inspire|teach|allow|permit|require|help)\s+(me|you|him|her|us|them|people|children|students)\s+to\s+\w+ing\b",
     2, "motivate sb to do，to 后面是原形"),
    ("g_perf_past_time", "时态",
     r"\b(have|has|'ve)\s+[^.?]{0,40}\b(in 19\d\d|in 20\d\d|last year|yesterday|two days ago)\b",
     3, "已经关掉的过去时间点用一般过去时"),
    ("g_from_child", "时间介词", r"\bfrom my (child|children|little)\b|\bfrom i was (a )?(child|kid|small)\b",
     2, "从过去持续到现在用 since I was a kid"),
    ("g_peoples", "可数性", r"\bpeoples\b", 2, "people 本身已是复数"),
    ("g_in_physically", "介词", r"\bin (physically|physical terms of the body)\b", 2, "副词前不加 in"),
    ("g_be_in_touch", "搭配", r"\b(didn't|don't|never|didn t)\s+(attach|attachment)\s+(with|to)?\s*(them|him|her|us)?\b",
     3, "「没联系」是 haven't been in touch with"),
    # --- 中式直译
    ("c_horizon_sing", "中式直译", r"\bbroaden(?:s|ing)?\s+(my|your|our|their|people'?s|a)\s+horizon\b",
     2, "horizons 永远复数"),
    ("c_high_paid", "中式直译", r"\bhigh-?paid\b", 2, "说 well-paid 或 high-paying"),
    ("c_do_choice", "搭配", r"\bdo(?:es|ing)?\s+(the same\s+|a\s+)?choice\b", 2, "choice 配 make，不配 do"),
    ("c_play_phone", "中式直译", r"\bplay(?:ing)?\s+(my|the|his|her|their)?\s?phone\b",
     2, "英语说 scroll (on) my phone / mess about on my phone"),
    ("c_learn_knowledge", "中式直译", r"\blearn knowledge\b", 2, "说 gain knowledge 或 learn things"),
    ("c_old_generation", "措辞", r"\bthe old generation\b", 1, "the older generation 更自然也更礼貌"),
    ("c_introvert_person", "词性", r"\ban? introvert person\b", 1, "说 I'm quite introverted"),
    ("c_emotion_for_mood", "词义", r"\b(my|the|his|her|one's)\s+emotion\b|\bdepends?\s+on\w*\s+my\s+emotion\b",
     2, "某一刻的心情是 mood；emotion 指喜怒哀惧"),
    ("c_scenery_for_situation", "词义", r"\bscener(y|ies)\b",
     2, "scenery 只指自然风景且不可数；「场合」是 situation / occasion"),
    ("c_organ_for_sense", "词义", r"\byour\s+(different|other|many)\s+organs?\b",
     2, "感官是 senses；organ 在英语里首先指内脏"),
    ("c_controller", "词义", r"\bcontroller\b", 1, "车上的是 steering wheel；controller 是游戏手柄"),
    ("c_identity_symbol", "词义", r"\bidentity\s+(symbol|simple|thing|sign)\b", 2, "身份象征是 status symbol"),
    ("c_get_rid_reverse", "词义反向", r"\b(can|could|will|always)\s+get rid of\b",
     3, "get rid of 是「甩掉/戒掉」，想表达「离不开」要说 can't do without"),
    ("c_in_this_area", "词义", r"\bin this area,?\s+i\b", 1, "如果想说「在这个时代」，是 in this era"),
    ("c_more_things", "量词", r"\bmuch things\b|\bso many thing\b", 3, "things 可数，用 many"),
    ("c_kind_of_noun", "含糊限定",
     r"\b(kind of|sort of|a kind of|kinda)\s+(a|an)?\s*\w*\s*(teacher|friend|person|place|thing|job|city|way)\b",
     2, "kind of 后面不能这样套名词；想说「算不上」用 I wouldn't exactly call it a ..."),
    ("c_no_such_thing", "否定含糊",
     r"\bdon'?t have\s+(a\s+)?(kind of|really|particular)?\s*(favorite|favourite)\s+\w+\b",
     2, "自然说法是 I don't really have a favourite ... ，really 放在 have 前面"),
    ("c_interacts_noun", "词性", r"\b(common|daily|usual|normal)\s+interacts?\b|\bjust interacts?\b",
     2, "interact 是动词，名词是 interaction(s)；这里更自然是 the usual exchanges"),
    ("c_teach_knowledge", "中式直译", r"\b(teach|taught|teaches)\s+(me|us|him|her|them)\s+knowledge\b",
     2, "teach me knowledge 不成立；说 teach me things 或 pass on knowledge"),
    ("c_deep_relationship", "搭配", r"\ba (deep|high) relationship\b", 1, "关系好用 close relationship；deep 偏中文「关系深」"),
    ("c_sit_on_chair", "介词", r"\bsit on (my|the|his|her) chair\b", 1, "带扶手的椅子用 in the chair；on the chair 听着像刚放下东西"),
]

FILLERS = {
    "you know": r"\byou know\b",
    "like（填充）": r"\blike\b",
    "kind of / sort of": r"\bkind of\b|\bsort of\b",
    "actually": r"\bactually\b",
    "stuff / things": r"\bstuff\b|\bthings\b",
}

VAGUE = r"\bstuff\b|\bstuff like that\b|\band so on\b|\bthe actual things\b|\bsome thing\b|\bsome things\b"

CONCESSION = (r"\bhowever\b|\balthough\b|\bthat said\b|\bhaving said that\b|\bon the other hand\b"
              r"|\bwhereas\b|\bnevertheless\b|\badmittedly\b|\bto some extent\b|\bit depends\b")
ADVANCE = r"\bmoreover\b|\bfurthermore\b|\bbesides\b|\bin addition\b|\bon top of that\b"
OPINION_MARKERS = {
    "I think": r"\bi think\b",
    "I'd say": r"\bi('d| would) say\b",
    "in my opinion": r"\bin my opinion\b",
    "the way I see it": r"\bthe way i see it\b",
    "from where I stand": r"\bfrom where i stand\b",
    "personally": r"\bpersonally\b",
    "it seems to me": r"\bit seems to me\b",
}

STOP = set("the a an and or but of to in on at for with from by as is are was were be been it this "
           "that i you he she we they my your his her our their me him them us so do does did have "
           "has had would could should will than then there here who which what some any one about "
           "into because not very really just like know think yeah okay answer question".split())

WORD = re.compile(r"[A-Za-z][A-Za-z']*\b")


def analyse(question: str, answer: str) -> dict:
    low = answer.lower()
    words = WORD.findall(answer)
    n = max(1, len(words))
    clauses = [c for c in (s.strip() for s in re.split(r"[.!?。]+", answer)) if c]
    lens = [len(WORD.findall(c)) for c in clauses] or [0]

    issues = []
    for rid, family, pat, impact, why in RULES:
        hits = [m.group(0).strip() for m in re.finditer(pat, low, re.I)]
        if hits:
            uniq = sorted({h.lower() for h in hits})
            issues.append({
                "rule_id": rid, "family": family, "impact": impact, "count": len(hits),
                "score": len(hits) * impact, "examples": uniq[:4], "why_zh": why,
            })
    issues.sort(key=lambda x: (-x["score"], x["rule_id"]))

    fillers = {k: len(re.findall(p, low)) for k, p in FILLERS.items()}
    filler_total = sum(fillers.values())
    opinion = {k: len(re.findall(p, low)) for k, p in OPINION_MARKERS.items()}
    used_opinion = sorted(k for k, v in opinion.items() if v)
    repeated = [w for w, c in Counter(w for w in (x.lower() for x in words)
                                      if len(w) > 3 and w not in STOP).most_common(6) if c >= 4]

    first12 = " ".join(words[:12]).lower()
    structure = {
        "有立场": bool(re.search(
            r"\b(yes|no|not really|absolutely|definitely|i (think|'d say|would say)|"
            r"to be honest|kind of|i don'?t)\b", first12)),
        "给理由": bool(re.search(r"\bbecause\b|\bsince\b|\bthe reason\b|\bdue to\b|\bwhich means\b", low)),
        "举例子": bool(re.search(
            r"\bfor example\b|\bfor instance\b|\bsuch as\b|\bin my case\b|\btake\b|"
            r"\blast (week|time|year)\b|\bwhen i was\b", low)),
        "作让步": bool(re.search(CONCESSION, low)),
        "再推进": bool(re.search(ADVANCE, low)),
    }
    missing = [k for k, v in structure.items() if not v]
    filler_rate = filler_total * 100 / n

    return {
        "question": question.strip(),
        "words": len(words),
        "metrics": {
            "filler_hits": fillers,
            "filler_per_100_words": round(filler_rate, 2),
            "vague_nouns": len(re.findall(VAGUE, low)),
            "concession_markers": len(re.findall(CONCESSION, low)),
            "advance_markers": len(re.findall(ADVANCE, low)),
            "opinion_markers": opinion,
            "opinion_variety": len(used_opinion),
            "mean_clause_words": round(sum(lens) / len(lens), 1),
            "longest_clause_words": max(lens),
            "repeated_content_words": repeated,
        },
        "structure": structure,
        "missing_moves": missing,
        "issues": issues,
        "top3_suggested": [i["rule_id"] for i in issues[:3]],
        "warnings": _warnings(len(words), issues, filler_rate, missing),
    }


def _warnings(words: int, issues: list, filler_rate: float, missing: list) -> list[str]:
    out = []
    if words < 25:
        out.append(f"回答只有 {words} 词，Part 1 也偏短；先确认这是完整回答而不是半句")
    if filler_rate > 1.0:
        out.append(f"填充词密度 {filler_rate:.2f}/百词，母语者 casual 口语约 0.2–0.5——"
                   "这一项比任何单个语法错都更影响流利度分")
    if "作让步" in missing:
        out.append("全篇没有让步或转折连接词，Part 3 逻辑层次上不去")
    if not issues:
        out.append("规则包一个都没命中——要么这份回答确实干净（那这一轮就只练语块和结构），"
                   "要么规则包需要扩充，别硬凑三个纠错点")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="单题口语诊断（确定性，不调用任何模型）")
    ap.add_argument("--question", required=True)
    ap.add_argument("--answer")
    ap.add_argument("--answer-file")
    ap.add_argument("--json", help="把结果写到指定文件")
    ap.add_argument("--top", type=int, default=6, help="打印前 N 个问题")
    args = ap.parse_args()

    if args.answer_file:
        answer = Path(args.answer_file).read_text(encoding="utf-8", errors="ignore")
    elif args.answer:
        answer = args.answer
    else:
        ap.error("必须给 --answer 或 --answer-file")

    report = analyse(args.question, answer)
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    m = report["metrics"]
    print(f"回答长度：{report['words']} 词 | 平均小句 {m['mean_clause_words']} 词"
          f"（最长 {m['longest_clause_words']}）")
    print(f"填充词：{m['filler_per_100_words']}/百词  {m['filler_hits']}")
    print(f"模糊名词 {m['vague_nouns']} 次 | 让步连接词 {m['concession_markers']} 次 | "
          f"推进连接词 {m['advance_markers']} 次 | 观点标记种类 {m['opinion_variety']}")
    print(f"结构：{report['structure']}")
    if report["missing_moves"]:
        print(f"缺失动作：{', '.join(report['missing_moves'])}")
    if m["repeated_content_words"]:
        print(f"重复用词（≥4 次）：{', '.join(m['repeated_content_words'])}")
    print(f"\n命中 {len(report['issues'])} 类问题，按分数损失排序：")
    for i in report["issues"][:args.top]:
        print(f"  [{i['score']:>3}] {i['family']} · {i['rule_id']} ×{i['count']}  "
              f"例：{'; '.join(i['examples'])[:60]}")
        print(f"        → {i['why_zh']}")
    for w in report["warnings"]:
        print(f"! {w}")
    print(f"\n建议这一轮只修：{', '.join(report['top3_suggested']) or '（无命中）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
