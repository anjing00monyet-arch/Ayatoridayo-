"""Decode submissions/candidate/main.py's frozen 719-step _ACTIONS script
into a Japanese natural-language log (one file per turn, grouped by day).

Read-only, offline decoder -- not part of the agent or the improvement
loop. Regenerate reports/candidate_actions_ja.md with:
    python3 reports/candidate_actions_ja.py
"""
import importlib.util

ITEM_JA = {
    "WHEAT": "小麦", "CARROT": "にんじん", "TOMATO": "トマト",
    "STRAWBERRY": "いちご", "MELON": "メロン", "EGG": "卵",
    "MILK": "牛乳", "WOOL": "羊毛", "FERTILIZER": "肥料",
    "SHEEP": "羊", "COW": "牛", "GOOSE": "ガチョウ",
}

DIR_JA = {"NORTH": "北", "SOUTH": "南", "EAST": "東", "WEST": "西"}
ANIMALS = {"SHEEP", "COW", "GOOSE"}


def item_ja(name):
    return ITEM_JA.get(name, name)


def counter_ja(name):
    return "匹" if name in ANIMALS else "個"


def unit_action_ja(order):
    if not order:
        return "何もしない"
    op = order[0]
    if op == "PASS":
        return "何もしない"
    if op in DIR_JA:
        return f"{DIR_JA[op]}へ移動"
    if op == "PICKUP":
        item, qty = order[1], order[2]
        return f"{item_ja(item)}を{qty}{counter_ja(item)}拾う"
    if op == "DROP":
        return "手持ちの荷物を置く"
    if op == "PLACE":
        return f"{item_ja(order[1])}を配置する"
    if op == "PLANT":
        return f"{item_ja(order[1])}の種をまく"
    if op == "WATER":
        return "水やりする"
    if op == "HARVEST":
        return "収穫する"
    if op == "CARE":
        return "動物の世話をする"
    if op == "FEED":
        return "動物に餌をやる"
    if op == "BUILD_PASTURE":
        return "牧草地/畜舎を建設する"
    if op == "COLLECT_FERTILIZER":
        return "肥料を集める"
    if op == "FERTILIZE":
        return "畑に肥料をまく"
    if op == "DIG":
        return "雑草を掘り起こす(除草)"
    return f"{op} {order[1:]}".strip()


def market_order_ja(order):
    if not order:
        return None
    op = order[0]
    if op == "HIRE":
        return ("雇用", 1)
    if op == "BUY_LAND":
        return ("土地購入", 1)
    if op == "BUY_ANIMAL":
        item, qty = order[1], order[2]
        return (f"{item_ja(item)}を{qty}匹購入", 0)
    if op == "BUY_SEED":
        item, qty = order[1], order[2]
        return (f"{item_ja(item)}の種を{qty}個購入", 0)
    if op == "BUY_PRODUCT":
        item, qty = order[1], order[2]
        return (f"{item_ja(item)}を{qty}個市場から購入", 0)
    if op == "SELL":
        item, qty = order[1], order[2]
        return (f"{item_ja(item)}を{qty}個売却", 0)
    return (str(order), 0)


def market_summary_ja(market):
    hires = sum(1 for o in market if o and o[0] == "HIRE")
    lands = sum(1 for o in market if o and o[0] == "BUY_LAND")
    parts = []
    if hires:
        parts.append(f"雇い人を{hires}人雇用")
    if lands:
        parts.append(f"土地を{lands}区画購入")
    for order in market:
        if not order or order[0] in ("HIRE", "BUY_LAND"):
            continue
        text, _ = market_order_ja(order)
        parts.append(text)
    return parts


def load_actions(path):
    spec = importlib.util.spec_from_file_location("cand_ja", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._ACTIONS


def is_noop(action):
    farmer = action.get("farmer") or ["PASS"]
    hands = action.get("hands") or []
    market = action.get("market") or []
    if farmer[0] != "PASS":
        return False
    if any((h or ["PASS"])[0] != "PASS" for h in hands):
        return False
    if market:
        return False
    return True


def turn_lines(step, action):
    day = step // 24 + 1
    turn = step % 24 + 1
    lines = [f"### {day}日目 ターン{turn} (step {step})"]
    farmer = action.get("farmer") or ["PASS"]
    lines.append(f"- 農場主: {unit_action_ja(farmer)}")
    for i, hand in enumerate(action.get("hands") or [], start=1):
        hand = hand or ["PASS"]
        if hand[0] == "PASS":
            continue
        lines.append(f"- 雇い人{i}: {unit_action_ja(hand)}")
    market_parts = market_summary_ja(action.get("market") or [])
    if market_parts:
        lines.append(f"- 市場: {'、'.join(market_parts)}")
    return lines


def build_report(actions):
    out = [
        "# candidate/main.py の行動ログ(自然言語)",
        "",
        "submissions/candidate/main.py の凍結スクリプト `_ACTIONS`"
        "(719ターン分)を自動生成した日本語の実況ログです。",
        "全員が何もしない(PASS)だけのターンはまとめて省略表記しています。",
        "",
    ]
    day = None
    noop_run_start = None

    def flush_noop(end_step):
        if noop_run_start is None:
            return
        if noop_run_start == end_step:
            out.append(f"### {noop_run_start // 24 + 1}日目 ターン{noop_run_start % 24 + 1} "
                       f"(step {noop_run_start}): 全員何もしない")
        else:
            out.append(
                f"### step {noop_run_start}〜{end_step - 1}: "
                f"全員何もしないターンが{end_step - noop_run_start}回続く"
            )
        out.append("")

    for step, action in enumerate(actions):
        d = step // 24 + 1
        if d != day:
            flush_noop(step)
            noop_run_start = None
            day = d
            out.append(f"\n## {d}日目\n")
        if is_noop(action):
            if noop_run_start is None:
                noop_run_start = step
            continue
        flush_noop(step)
        noop_run_start = None
        out.extend(turn_lines(step, action))
        out.append("")
    flush_noop(len(actions))
    return "\n".join(out)


if __name__ == "__main__":
    actions = load_actions("submissions/candidate/main.py")
    report = build_report(actions)
    with open("reports/candidate_actions_ja.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"wrote reports/candidate_actions_ja.md ({len(actions)} steps)")
