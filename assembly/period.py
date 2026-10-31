"""Period arithmetic. The news week starts on Sunday (it is the ISO week of the following day)."""
import datetime
from datetime import date


def week_id(day: date) -> str:
    y, w, _ = (day + datetime.timedelta(days=1)).isocalendar()
    return "%d-W%02d" % (y, w)
