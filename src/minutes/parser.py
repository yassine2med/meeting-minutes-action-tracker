"""Find action items in plain text meeting minutes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
_MONTH_RE = "|".join(m[:3] + "(?:" + m[3:] + ")?" if len(m) > 3 else m for m in MONTHS)
_WEEKDAY_RE = "|".join(d[:3] + "(?:" + d[3:] + ")?" for d in WEEKDAYS)

DATE_PHRASE = (
    r"(?:\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    rf"|(?:{_MONTH_RE})\.? \d{{1,2}}(?:st|nd|rd|th)?(?:,? \d{{4}})?"
    rf"|(?:next |this )?(?:{_WEEKDAY_RE})"
    r"|tomorrow|today|end of (?:the )?week|eow|end of (?:the )?month|eom|next week)"
)
DUE_RE = re.compile(rf"[,;(]?\s*\b(?:due(?: on| by)?|by|before|no later than|until|on|for)\s+({DATE_PHRASE})\b\)?[.,;]?", re.I)
MARKER_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?:(?P<box>\[[ xX]\])\s*|(?P<kw>action items?|action|ai|to-?do|task)\s*(?P<who>[\(\[][^)\]]+[\)\]])?\s*[:\-]\s*)(?P<text>.+)$", re.I)
SENTENCE_RE = re.compile(r"^\s*(?:[-*•]\s*)?(?P<names>[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}(?: (?:and|&) [A-Z][a-z]+(?: [A-Z][a-z]+)?)?) will (?P<text>.+)$")
OWNER_START_RE = re.compile(r"^(?P<names>[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}(?:(?:,| and| &) [A-Z][a-z]+(?: [A-Z][a-z]+)?)*) (?:to|will|should|must|needs to|is to) (?P<text>.+)$")
AT_RE = re.compile(r"@([A-Za-z][\w-]*)")
STOP_NAMES = {"It", "This", "That", "We", "They", "He", "She", "There", "The", "Next", "Bids", "Water", "Someone"}
HEADER_DATE_RE = re.compile(r"^\s*(?:meeting\s+)?date\s*:\s*(\d{4}-\d{2}-\d{2})", re.I | re.M)


@dataclass
class Item:
    number: int
    owner: str
    task: str
    due: date | None
    done: bool
    line: int

    @property
    def id(self) -> str:
        return f"A{self.number}"

    def as_dict(self) -> dict:
        return {"id": self.id, "owner": self.owner, "task": self.task,
                "due": self.due.isoformat() if self.due else "", "done": self.done, "line": self.line}


ATTENDEES_RE = re.compile(r"^\s*attendees?\s*:\s*(.+)$", re.I | re.M)


def attendees(text: str) -> dict[str, str]:
    """Map a first name to the full name from the Attendees line, only when the first name is unique."""
    match = ATTENDEES_RE.search(text)
    if not match:
        return {}
    full = [n.strip() for n in match.group(1).split(",") if n.strip()]
    firsts: dict[str, list[str]] = {}
    for name in full:
        firsts.setdefault(name.split()[0].lower(), []).append(name)
    return {first: names[0] for first, names in firsts.items() if len(names) == 1}


def meeting_date(text: str, fallback: date | None = None) -> date:
    match = HEADER_DATE_RE.search(text)
    if match:
        return date.fromisoformat(match.group(1))
    if fallback:
        return fallback
    raise ValueError("no 'Date: YYYY-MM-DD' line in the minutes; pass --meeting-date")


def _next_weekday(start: date, index: int) -> date:
    return start + timedelta(days=(index - start.weekday() - 1) % 7 + 1)


def parse_date(phrase: str, meeting: date) -> date | None:
    """Turn a date phrase into a date, using the meeting date for relative words."""
    p = phrase.strip().lower().rstrip(".,;)")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
        return date.fromisoformat(p)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", p)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else meeting.year
        year = year + 2000 if year < 100 else year
        try:
            found = date(year, month, day)
        except ValueError:
            return None
        if not m.group(3) and found < meeting:
            found = date(year + 1, month, day)
        return found
    m = re.fullmatch(rf"({_MONTH_RE})\.? (\d{{1,2}})(?:st|nd|rd|th)?(?:,? (\d{{4}}))?", p)
    if m:
        month = next(i for i, name in enumerate(MONTHS, start=1) if name.startswith(m.group(1)[:3]))
        year = int(m.group(3)) if m.group(3) else meeting.year
        try:
            found = date(year, month, int(m.group(2)))
        except ValueError:
            return None
        if not m.group(3) and found < meeting:
            found = date(year + 1, month, int(m.group(2)))
        return found
    if p == "today":
        return meeting
    if p == "tomorrow":
        return meeting + timedelta(days=1)
    if p in ("end of week", "end of the week", "eow"):
        friday = meeting + timedelta(days=(4 - meeting.weekday()) % 7)
        return friday if meeting.weekday() <= 4 else _next_weekday(meeting, 4)
    if p in ("end of month", "end of the month", "eom"):
        nxt = date(meeting.year + (meeting.month == 12), meeting.month % 12 + 1, 1)
        return nxt - timedelta(days=1)
    if p == "next week":
        return _next_weekday(meeting, 4) + timedelta(days=7) if meeting.weekday() > 4 else meeting + timedelta(days=(4 - meeting.weekday()) + 7)
    m = re.fullmatch(rf"(next |this )?({_WEEKDAY_RE})", p)
    if m:
        index = next(i for i, name in enumerate(WEEKDAYS) if name.startswith(m.group(2)[:3]))
        found = _next_weekday(meeting, index)
        return found + timedelta(days=7) if (m.group(1) or "").strip() == "next" else found
    return None


def _clean_names(names: str) -> str:
    parts = [n.strip() for n in re.split(r",| and | & ", names) if n.strip()]
    return ", ".join(parts)


def _finish(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,;:-.")
    text = re.sub(r"^(?:to|will|should)\s+", "", text, flags=re.I)
    return text[:1].upper() + text[1:] if text else text


def parse_minutes(text: str, meeting: date, markers_only: bool = False) -> list[Item]:
    """Extract action items. Lines recognised: ACTION, AI, TASK and TO-DO markers, checkboxes and 'Name will ...'."""
    items: list[Item] = []
    known = attendees(text)
    for number, line in enumerate(text.splitlines(), start=1):
        done = False
        owner = ""
        body = None
        m = MARKER_RE.match(line)
        if m:
            body = m.group("text")
            if m.group("box"):
                done = m.group("box").lower() == "[x]"
            if m.group("who"):
                owner = _clean_names(m.group("who").strip("()[] "))
        elif not markers_only:
            s = SENTENCE_RE.match(line)
            if s and s.group("names").split()[0] not in STOP_NAMES:
                owner, body = _clean_names(s.group("names")), s.group("text")
        if body is None:
            continue
        if re.search(r"\((?:done|completed)\)\s*$", body, re.I):
            done = True
            body = re.sub(r"\s*\((?:done|completed)\)\s*$", "", body, flags=re.I)
        due = None
        due_match = None
        for candidate in DUE_RE.finditer(body):
            parsed = parse_date(candidate.group(1), meeting)
            if parsed:
                due, due_match = parsed, candidate
        if due_match:
            body = body[:due_match.start()] + " " + body[due_match.end():]
        at = AT_RE.findall(body)
        if at and not owner:
            owner = _clean_names(" and ".join(at))
        body = AT_RE.sub("", body)
        if not owner:
            o = OWNER_START_RE.match(body.strip())
            if o and o.group("names").split()[0] not in STOP_NAMES:
                owner, body = _clean_names(o.group("names")), o.group("text")
        task = _finish(body)
        if not task:
            continue
        if owner:
            owner = ", ".join(known.get(n.lower(), n) if " " not in n else n for n in owner.split(", "))
        items.append(Item(len(items) + 1, owner or "(unassigned)", task, due, done, number))
    return items


def overdue(items: list[Item], today: date) -> list[Item]:
    return sorted((i for i in items if not i.done and i.due and i.due < today), key=lambda i: (i.due, i.id))


def problems(items: list[Item]) -> list[str]:
    out = []
    for i in items:
        if i.owner == "(unassigned)":
            out.append(f"{i.id} (line {i.line}): no owner: {i.task}")
        if i.due is None and not i.done:
            out.append(f"{i.id} (line {i.line}): no due date: {i.task}")
    return out
