"""Morpho HDL recursive-descent parser: tokens -> AST, per the grammar in
Frozen Specification v1.0.0 §7.B, as corrected by docs/CONTRADICTIONS.md
(#C1, #C2). Produces `morpho.ast.Document`; no semantic resolution
happens here (see `morpho/ir.py`).
"""

from __future__ import annotations

from typing import List, Optional

from morpho import ast
from morpho.lexer import Token, tokenize

KEYWORD_KINDS = {
    "MORPHO", "ENTITY", "RELATION", "DERIVED", "INFERRED", "FRAME",
    "TRANSFORM", "GROUP", "CONSTRAINT", "PROVENANCE", "VERSION",
    "FROM", "TO", "TYPE", "CONFIDENCE", "PARENT", "POSITION",
    "ORIENTATION", "SCALE", "MEMBERS", "ON", "RULE", "SOURCE",
    "ORIGIN_VERSION",
}


class ParseError(Exception):
    pass


class _Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise ParseError(
                f"expected {kind}, got {tok.kind} ({tok.value!r}) at line {tok.line}, col {tok.col}"
            )
        return self.advance()

    # -- document -----------------------------------------------------

    def parse_document(self) -> ast.Document:
        self.expect("MORPHO")
        morpho_version = self.expect("STRING").value
        self.expect("SEMI")
        declarations = []
        while self.peek().kind != "EOF":
            declarations.append(self._parse_declaration())
        return ast.Document(morpho_version=morpho_version, declarations=tuple(declarations))

    def _parse_declaration(self):
        kind = self.peek().kind
        if kind == "ENTITY":
            return self._parse_entity_decl()
        if kind in ("DERIVED", "INFERRED"):
            modifier = self.advance().value
            return self._parse_relation_decl(modifier)
        if kind == "RELATION":
            return self._parse_relation_decl(None)
        if kind == "FRAME":
            return self._parse_frame_decl()
        if kind == "GROUP":
            return self._parse_group_decl()
        if kind == "CONSTRAINT":
            return self._parse_constraint_decl()
        tok = self.peek()
        raise ParseError(f"unexpected token {tok.kind} ({tok.value!r}) at line {tok.line}, col {tok.col}")

    # -- entity ---------------------------------------------------------

    def _parse_entity_decl(self) -> ast.EntityDecl:
        self.expect("ENTITY")
        entity_id = self.expect("IDENT").value
        self.expect("LBRACE")
        attrs = []
        provenance: Optional[ast.ProvenanceBlock] = None
        while self.peek().kind != "RBRACE":
            if self.peek().kind == "PROVENANCE" and self.tokens[self.pos + 1].kind == "LBRACE":
                provenance = self._parse_provenance_block()
            else:
                attrs.append(self._parse_attr_stmt())
        self.expect("RBRACE")
        return ast.EntityDecl(id=entity_id, attrs=tuple(attrs), provenance=provenance)

    def _parse_attr_stmt(self) -> ast.AttrStmt:
        name_tok = self.advance()
        if name_tok.kind != "IDENT" and name_tok.kind not in KEYWORD_KINDS:
            raise ParseError(
                f"expected attribute name, got {name_tok.kind} at line {name_tok.line}, col {name_tok.col}"
            )
        # Contextual keyword resolution -- see docs/CONTRADICTIONS.md#C1.
        name = name_tok.value
        self.expect("COLON")
        value = self._parse_value()
        self.expect("SEMI")
        return ast.AttrStmt(name=name, value=value)

    def _parse_value(self):
        tok = self.peek()
        if tok.kind == "STRING":
            return self.advance().value
        if tok.kind == "NUMBER":
            return self.advance().value
        if tok.kind == "BOOL":
            return self.advance().value
        if tok.kind == "LBRACKET":
            return self._parse_vector3()
        if tok.kind == "PROVENANCE":
            return self._parse_provenance_block()
        raise ParseError(f"unexpected value token {tok.kind} at line {tok.line}, col {tok.col}")

    def _parse_vector3(self) -> ast.Vector3Literal:
        self.expect("LBRACKET")
        x = self.expect("NUMBER").value
        self.expect("COMMA")
        y = self.expect("NUMBER").value
        self.expect("COMMA")
        z = self.expect("NUMBER").value
        self.expect("RBRACKET")
        return ast.Vector3Literal(float(x), float(y), float(z))

    def _parse_quaternion(self) -> ast.QuaternionLiteral:
        self.expect("LBRACKET")
        x = self.expect("NUMBER").value
        self.expect("COMMA")
        y = self.expect("NUMBER").value
        self.expect("COMMA")
        z = self.expect("NUMBER").value
        self.expect("COMMA")
        w = self.expect("NUMBER").value
        self.expect("RBRACKET")
        return ast.QuaternionLiteral(float(x), float(y), float(z), float(w))

    def _parse_provenance_block(self) -> ast.ProvenanceBlock:
        self.expect("PROVENANCE")
        self.expect("LBRACE")
        self.expect("SOURCE")
        self.expect("COLON")
        source = self.expect("STRING").value
        self.expect("SEMI")
        self.expect("ORIGIN_VERSION")
        self.expect("COLON")
        origin_version = self.expect("STRING").value
        self.expect("SEMI")
        confidence = None
        if self.peek().kind == "CONFIDENCE":
            self.advance()
            self.expect("COLON")
            confidence = float(self.expect("NUMBER").value)
            self.expect("SEMI")
        self.expect("RBRACE")
        return ast.ProvenanceBlock(source=source, origin_version=origin_version, confidence=confidence)

    # -- relation -------------------------------------------------------

    def _parse_relation_decl(self, modifier: Optional[str]) -> ast.RelationDecl:
        self.expect("RELATION")
        relation_id = self.expect("IDENT").value
        self.expect("LBRACE")
        self.expect("FROM")
        self.expect("COLON")
        from_ref = self.expect("STRING").value
        self.expect("SEMI")
        self.expect("TO")
        self.expect("COLON")
        to_ref = self.expect("STRING").value
        self.expect("SEMI")
        self.expect("TYPE")
        self.expect("COLON")
        # STRING, not IDENT -- see docs/CONTRADICTIONS.md#C3.
        rel_type = self.expect("STRING").value
        self.expect("SEMI")
        confidence = None
        if self.peek().kind == "CONFIDENCE":
            self.advance()
            self.expect("COLON")
            confidence = float(self.expect("NUMBER").value)
            self.expect("SEMI")
        provenance = None
        if self.peek().kind == "PROVENANCE":
            provenance = self._parse_provenance_block()
        self.expect("RBRACE")
        return ast.RelationDecl(
            id=relation_id,
            from_ref=from_ref,
            to_ref=to_ref,
            type=rel_type,
            modifier=modifier,
            confidence=confidence,
            provenance=provenance,
        )

    # -- frame ------------------------------------------------------------

    def _parse_frame_decl(self) -> ast.FrameDecl:
        self.expect("FRAME")
        frame_id = self.expect("IDENT").value
        self.expect("LBRACE")
        parent = None
        if self.peek().kind == "PARENT":
            self.advance()
            self.expect("COLON")
            parent = self.expect("STRING").value
            self.expect("SEMI")
        self.expect("POSITION")
        self.expect("COLON")
        position = self._parse_vector3()
        self.expect("SEMI")
        orientation = None
        if self.peek().kind == "ORIENTATION":
            self.advance()
            self.expect("COLON")
            orientation = self._parse_quaternion()
            self.expect("SEMI")
        scale = None
        if self.peek().kind == "SCALE":
            self.advance()
            self.expect("COLON")
            scale = self._parse_vector3()
            self.expect("SEMI")
        self.expect("RBRACE")
        return ast.FrameDecl(id=frame_id, position=position, parent=parent, orientation=orientation, scale=scale)

    # -- group ------------------------------------------------------------

    def _parse_group_decl(self) -> ast.GroupDecl:
        self.expect("GROUP")
        group_id = self.expect("IDENT").value
        self.expect("LBRACE")
        self.expect("MEMBERS")
        self.expect("COLON")
        self.expect("LBRACKET")
        members = [self.expect("STRING").value]
        while self.peek().kind == "COMMA":
            self.advance()
            members.append(self.expect("STRING").value)
        self.expect("RBRACKET")
        self.expect("SEMI")
        self.expect("RBRACE")
        return ast.GroupDecl(id=group_id, members=tuple(members))

    # -- constraint --------------------------------------------------------

    def _parse_constraint_decl(self) -> ast.ConstraintDecl:
        self.expect("CONSTRAINT")
        constraint_id = self.expect("IDENT").value
        self.expect("LBRACE")
        self.expect("ON")
        self.expect("COLON")
        on = self.expect("STRING").value
        self.expect("SEMI")
        self.expect("RULE")
        self.expect("COLON")
        rule = self.expect("STRING").value
        self.expect("SEMI")
        self.expect("RBRACE")
        return ast.ConstraintDecl(id=constraint_id, on=on, rule=rule)


def parse_document(source: str) -> ast.Document:
    tokens = tokenize(source)
    return _Parser(tokens).parse_document()
