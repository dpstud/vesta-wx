SUBWAY_TRUNK_COLORS = {
    "A": "{67}", "C": "{67}", "E": "{67}",
    "B": "{64}", "D": "{64}", "F": "{64}", "M": "{64}",
    "N": "{65}", "Q": "{65}", "R": "{65}", "W": "{65}",
    "1": "{63}", "2": "{63}", "3": "{63}",
    "4": "{66}", "5": "{66}", "6": "{66}",
    "7": "{68}",
    "L": "{69}", "S": "{69}",
}

def format_train_slot(route: str, mins: int) -> str:
    color = SUBWAY_TRUNK_COLORS.get(route.upper(), "{67}")
    r = route.upper()[:1]
    if mins < 10:
        return f"{color}{r} {mins}M"
    else:
        m = str(min(mins, 99))
        return f"{color}{r}{m}M"

def format_countdown_row(direction: str, t1: tuple = None, t2: tuple = None) -> str:
    s1 = format_train_slot(*t1) if t1 else "     "
    s2 = format_train_slot(*t2) if t2 else "     "
    return f"{direction}: {s1} {s2}"

def get_subway_countdown() -> list[str]:
    row1 = "  50TH ST C/E  "
    row2 = format_countdown_row("UP", ("C", 2), ("E", 7))
    row3 = format_countdown_row("DN", ("E", 4), ("F", 6))
    return [row1, row2, row3]
