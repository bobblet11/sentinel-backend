def indent_with_tab(s: str):
    return f"\t{s}"


def indent_with_space(s: str):
    return f"        {s}"


def prRed(s: str):
    return "\033[91m{}\033[00m".format(s)


def prGreen(s: str):
    return "\033[92m{}\033[00m".format(s)


def prYellow(s: str):
    return "\033[93m{}\033[00m".format(s)


def prLightPurple(s: str):
    return "\033[94m{}\033[00m".format(s)


def prPurple(s: str):
    return "\033[95m{}\033[00m".format(s)


def prCyan(s: str):
    return "\033[96m{}\033[00m".format(s)


def prLightGray(s: str):
    return "\033[97m{}\033[00m".format(s)
