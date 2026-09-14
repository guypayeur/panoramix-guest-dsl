"""Minimal YAML 1.1 subset (stdlib only) for catalog graphs + editor I/O.

Intention: import/export the *shape* of getafix-seed-paul dsl-gui specs
(data / execution / calculations) without PyYAML or a dsl-gui lift.
Supports mappings, sequences, scalars, comments, simple flow
collections, and `|` / `>` block scalars used by seed domain YAML.
Not a full YAML 1.1 implementation.
"""

from __future__ import annotations

import re
from typing import Any

from dsl.errors import InvalidYaml

_COMMENT = re.compile(r"(^|[\s])#.*$")
_KEY = re.compile(r"^([^:]+?)\s*:(?:\s+(.*))?$")
_BLOCK_INDICATOR = re.compile(r"^([|>])([+-]?)(\d*)$")
_BOOLS = {"true": True, "false": False, "yes": True, "no": False}
_NULLS = {"null", "~", ""}


class _Cursor:
    def __init__(self, lines: list[tuple[int, str]]) -> None:
        self.lines = lines
        self.i = 0

    def peek(self) -> tuple[int, str] | None:
        if self.i >= len(self.lines):
            return None
        return self.lines[self.i]

    def pop(self) -> tuple[int, str]:
        row = self.lines[self.i]
        self.i += 1
        return row


def loads(text: str) -> Any:
    """Parse a YAML subset document. Empty / comment-only → empty mapping."""
    if text is None:
        raise InvalidYaml("yaml text is required")
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[tuple[int, str]] = []
    for lineno, line in enumerate(raw.split("\n"), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line[indent:]
        if content.startswith("\t"):
            raise InvalidYaml(f"line {lineno}: tabs are not allowed")
        lines.append((indent, content.rstrip()))
    if not lines:
        return {}
    cur = _Cursor(lines)
    try:
        value = _parse_value(cur, indent=lines[0][0])
    except InvalidYaml:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise InvalidYaml(str(exc)) from exc
    if cur.peek() is not None:
        leftover = cur.peek()
        raise InvalidYaml(f"unexpected content at indent {leftover[0]}: {leftover[1]!r}")
    return value


def dumps(value: Any) -> str:
    """Emit a stable block-style YAML subset document."""
    if value is None:
        return "null\n"
    lines = _dump(value, indent=0)
    text = "\n".join(lines).rstrip() + "\n"
    return text


def _parse_value(cur: _Cursor, indent: int) -> Any:
    peeked = cur.peek()
    if peeked is None:
        return None
    if peeked[0] < indent:
        return None
    if peeked[1].startswith("- ") or peeked[1] == "-":
        return _parse_seq(cur, indent)
    return _parse_map(cur, indent)


def _parse_map(cur: _Cursor, indent: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    while True:
        peeked = cur.peek()
        if peeked is None or peeked[0] < indent:
            break
        if peeked[0] > indent:
            raise InvalidYaml(f"unexpected indent for mapping entry: {peeked[1]!r}")
        if peeked[1].startswith("- ") or peeked[1] == "-":
            raise InvalidYaml(f"sequence item where mapping expected: {peeked[1]!r}")
        _indent, content = cur.pop()
        key, inline = _split_key(content)
        if key in out:
            # last-key-wins (PyYAML / seed loadSpecYaml intention)
            pass
        if inline is None:
            nxt = cur.peek()
            if nxt is None or nxt[0] < indent:
                out[key] = None
            elif nxt[0] == indent and (nxt[1].startswith("- ") or nxt[1] == "-"):
                # YAML 1.1: `key:\n- item` — sequence value at the key indent.
                out[key] = _parse_seq(cur, indent)
            elif nxt[0] > indent:
                out[key] = _parse_value(cur, nxt[0])
            else:
                out[key] = None
        elif _is_block_indicator(inline):
            out[key] = _parse_block_scalar(cur, indent, inline)
        else:
            out[key] = _parse_scalar(inline)
    return out


def _parse_seq(cur: _Cursor, indent: int) -> list[Any]:
    out: list[Any] = []
    while True:
        peeked = cur.peek()
        if peeked is None or peeked[0] < indent:
            break
        if peeked[0] > indent:
            raise InvalidYaml(f"unexpected indent for sequence item: {peeked[1]!r}")
        if not (peeked[1].startswith("- ") or peeked[1] == "-"):
            break
        _indent, content = cur.pop()
        rest = _strip_comment(content[1:].lstrip())
        if not rest:
            nxt = cur.peek()
            if nxt is None or nxt[0] <= indent:
                out.append(None)
            else:
                out.append(_parse_value(cur, nxt[0]))
            continue
        if _looks_like_key(rest):
            key, inline = _split_key(rest)
            item: dict[str, Any] = {}
            if inline is None:
                nxt = cur.peek()
                item[key] = (
                    _parse_value(cur, nxt[0])
                    if nxt is not None and nxt[0] > indent
                    else None
                )
            elif _is_block_indicator(inline):
                item[key] = _parse_block_scalar(cur, indent, inline)
            else:
                item[key] = _parse_scalar(inline)
            nxt = cur.peek()
            while nxt is not None and nxt[0] > indent and not (
                nxt[1].startswith("- ") or nxt[1] == "-"
            ):
                more = _parse_map(cur, nxt[0])
                item.update(more)
                nxt = cur.peek()
            out.append(item)
        else:
            out.append(_parse_scalar(rest))
    return out


def _looks_like_key(text: str) -> bool:
    if text[:1] in ("'", '"', "[", "{"):
        return False
    match = _KEY.match(text)
    return match is not None and not text.startswith("- ")


def _split_key(content: str) -> tuple[str, str | None]:
    match = _KEY.match(content)
    if not match:
        raise InvalidYaml(f"expected 'key:' got {content!r}")
    key = match.group(1).strip()
    if (key.startswith("'") and key.endswith("'")) or (
        key.startswith('"') and key.endswith('"')
    ):
        key = key[1:-1]
    rest = match.group(2)
    if rest is None or rest == "":
        return key, None
    rest = _strip_comment(rest)
    if rest == "":
        return key, None
    return key, rest


def _strip_comment(text: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or text[i - 1].isspace():
                return text[:i].rstrip()
    return text.rstrip()


def _is_block_indicator(text: str) -> bool:
    return bool(_BLOCK_INDICATOR.fullmatch((text or "").strip()))


def _parse_block_scalar(cur: _Cursor, key_indent: int, indicator: str) -> str:
    """YAML `|` / `>` block scalar (seed formula / note lines)."""
    match = _BLOCK_INDICATOR.fullmatch((indicator or "").strip())
    style = match.group(1) if match else "|"
    lines: list[str] = []
    block_indent: int | None = None
    while True:
        peeked = cur.peek()
        if peeked is None or peeked[0] <= key_indent:
            break
        indent, content = cur.pop()
        if block_indent is None:
            block_indent = indent
        extra = max(indent - block_indent, 0)
        lines.append((" " * extra) + content)
    if style == ">":
        return " ".join(part.strip() for part in lines if part.strip())
    return "\n".join(lines)


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] in ("'", '"'):
        return _unquote(text)
    if text[0] == "[" and text.endswith("]"):
        return _parse_flow_seq(text[1:-1])
    if text[0] == "{" and text.endswith("}"):
        return _parse_flow_map(text[1:-1])
    lower = text.lower()
    if lower in _NULLS:
        return None
    if lower in _BOOLS:
        return _BOOLS[lower]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _unquote(text: str) -> str:
    quote = text[0]
    if len(text) < 2 or text[-1] != quote:
        raise InvalidYaml(f"unterminated string: {text!r}")
    inner = text[1:-1]
    if quote == "'":
        return inner.replace("''", "'")
    out: list[str] = []
    esc = False
    for ch in inner:
        if esc:
            out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(ch, ch))
            esc = False
        elif ch == "\\":
            esc = True
        else:
            out.append(ch)
    return "".join(out)


def _split_flow(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            continue
        if not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_flow_seq(text: str) -> list[Any]:
    if not text.strip():
        return []
    return [_parse_scalar(part) for part in _split_flow(text)]


def _parse_flow_map(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    out: dict[str, Any] = {}
    for part in _split_flow(text):
        key, inline = _split_key(part if ":" in part else f"{part}:")
        out[key] = None if inline is None else _parse_scalar(inline)
    return out


def _dump(value: Any, indent: int) -> list[str]:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{pad}{{}}"]
        lines: list[str] = []
        for key, item in value.items():
            rendered = _dump_key(key)
            if _is_scalar(item):
                lines.append(f"{pad}{rendered}: {_dump_scalar(item)}")
            elif item == []:
                lines.append(f"{pad}{rendered}: []")
            elif item == {}:
                lines.append(f"{pad}{rendered}: {{}}")
            else:
                lines.append(f"{pad}{rendered}:")
                lines.extend(_dump(item, indent + 1))
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}[]"]
        lines = []
        for item in value:
            if _is_scalar(item):
                lines.append(f"{pad}- {_dump_scalar(item)}")
            elif isinstance(item, dict):
                if not item:
                    lines.append(f"{pad}- {{}}")
                    continue
                first = True
                for key, nested in item.items():
                    rendered = _dump_key(key)
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if _is_scalar(nested):
                        lines.append(f"{prefix}{rendered}: {_dump_scalar(nested)}")
                    elif nested == []:
                        lines.append(f"{prefix}{rendered}: []")
                    elif nested == {}:
                        lines.append(f"{prefix}{rendered}: {{}}")
                    else:
                        lines.append(f"{prefix}{rendered}:")
                        # Nested blocks under a sequence-item key sit two
                        # levels past the list indent (`- ` plus one map step).
                        lines.extend(_dump(nested, indent + 2))
            else:
                lines.append(f"{pad}-")
                lines.extend(_dump(item, indent + 1))
        return lines
    return [f"{pad}{_dump_scalar(value)}"]


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def _dump_key(key: Any) -> str:
    text = str(key)
    if _needs_quote(text):
        return json_quote(text)
    return text


def _dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    if _needs_quote(text):
        return json_quote(text)
    return text


def _needs_quote(text: str) -> bool:
    if text == "" or text.strip() != text:
        return True
    if text.lower() in _BOOLS or text.lower() in _NULLS:
        return True
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return True
    if text[:1] in ("'", '"', "[", "{", "&", "*", "!", "|", ">", "%", "@", "`"):
        return True
    if any(ch in text for ch in (":", "#", ",", "\n")):
        return True
    return False


def json_quote(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
