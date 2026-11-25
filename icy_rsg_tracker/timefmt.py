"""Converting between milliseconds and the M:SS.mmm text used in the CSVs."""


def format_ms(ms):
    """12345678 -> '205:45.678'. Minutes are not wrapped into hours. None -> ''."""
    if ms is None:
        return ""
    ms = int(ms)
    minutes, rem = divmod(ms, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def parse_time(text):
    """'205:45.678' -> 12345678. '' -> None."""
    if not text:
        return None
    minutes, rest = text.split(":")
    seconds, millis = rest.split(".")
    return int(minutes) * 60_000 + int(seconds) * 1000 + int(millis)
