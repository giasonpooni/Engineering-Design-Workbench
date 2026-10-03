"""Morpho HDL lexer, matching the lexical structure in Frozen
Specification v1.0.0 §7.A.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

KEYWORDS = {
    "morpho", "entity", "relation", "derived", "inferred", "frame",
    "transform", "group", "constraint", "provenance", "version",
    "from", "to", "type", "confidence", "parent", "position",
    "orientation", "scale", "members", "on", "rule",
    # "source" and "origin_version" are used as fixed literal keywords by
    # provenance_block (§7.B) but were missing from this list in the
    # frozen spec's own §7.A -- see docs/CONTRADICTIONS.md#C2.
    "source", "origin_version",
}


@dataclass(frozen=True)
class Token:
    kind: str  # KEYWORD text (upper-cased) | IDENT | STRING | NUMBER | BOOL | punctuation kind | EOF
    value: object
    line: int
    col: int


class LexError(Exception):
    pass


_TOKEN_RE = re.compile(
    r"""
    (?P<WS>[ \t\r\n]+)
  | (?P<LINECOMMENT>//[^\n]*)
  | (?P<BLOCKCOMMENT>/\*.*?\*/)
  | (?P<STRING>"(?:[^"\\]|\\.)*")
  | (?P<NUMBER>-?\d+(\.\d+)?([eE][+-]?\d+)?)
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<LBRACE>\{)
  | (?P<RBRACE>\})
  | (?P<LBRACKET>\[)
  | (?P<RBRACKET>\])
  | (?P<COLON>:)
  | (?P<SEMI>;)
  | (?P<COMMA>,)
    """,
    re.VERBOSE | re.DOTALL,
)


def tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    line = 1
    col = 1
    pos = 0
    length = len(source)

    while pos < length:
        match = _TOKEN_RE.match(source, pos)
        if match is None:
            raise LexError(f"unexpected character {source[pos]!r} at line {line}, col {col}")
        kind = match.lastgroup
        text = match.group()

        if kind == "WS":
            newlines = text.count("\n")
            if newlines:
                line += newlines
                col = len(text) - text.rfind("\n")
            else:
                col += len(text)
            pos = match.end()
            continue
        if kind in ("LINECOMMENT", "BLOCKCOMMENT"):
            newlines = text.count("\n")
            if newlines:
                line += newlines
                col = len(text) - text.rfind("\n")
            else:
                col += len(text)
            pos = match.end()
            continue

        start_line, start_col = line, col

        if kind == "STRING":
            value = _unescape_string(text[1:-1])
            tokens.append(Token("STRING", value, start_line, start_col))
        elif kind == "NUMBER":
            value = float(text) if ("." in text or "e" in text or "E" in text) else int(text)
            tokens.append(Token("NUMBER", value, start_line, start_col))
        elif kind == "IDENT":
            if text == "true":
                tokens.append(Token("BOOL", True, start_line, start_col))
            elif text == "false":
                tokens.append(Token("BOOL", False, start_line, start_col))
            elif text in KEYWORDS:
                tokens.append(Token(text.upper(), text, start_line, start_col))
            else:
                tokens.append(Token("IDENT", text, start_line, start_col))
        else:
            tokens.append(Token(kind, text, start_line, start_col))

        col += len(text)
        pos = match.end()

    tokens.append(Token("EOF", None, line, col))
    return tokens


def _unescape_string(body: str) -> str:
    return body.replace('\\"', '"').replace("\\\\", "\\")
