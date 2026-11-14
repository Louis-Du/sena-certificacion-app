"""HTML restringido para las estrategias del Informe de Gestión.

El editor de la UI produce un subconjunto pequeño de HTML: párrafos, saltos de
línea, negrita, cursiva y listas. Este módulo centraliza dos responsabilidades:

* ``sanitize_estrategia_html`` limpia cualquier entrada antes de persistirla o
  devolverla por API (allowlist de etiquetas, sin atributos ni contenido
  ejecutable).
* ``html_to_docx_paragraphs`` traduce ese HTML a párrafos y runs de
  ``python-docx`` sin volcar marcado como texto visible.

Los textos históricos se conservan: si venían en Markdown (``**negrita**``,
``1\\.``, viñetas) se interpretan al exportar; si son plano simple se insertan
como párrafos normales.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.text.paragraph import Paragraph

# Único subconjunto aceptado por la API y por el DOCX.
_ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li"}
_TAG_ALIASES = {"b": "strong", "i": "em", "div": "p"}
_DROP_CONTENT_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "svg",
    "math",
    "template",
    "noscript",
    "form",
    "input",
    "button",
    "audio",
    "video",
    "canvas",
}
_TAG_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")


def sanitize_estrategia_html(value: Any) -> str:
    """Devuelve HTML permitido o el texto plano histórico sin cambios.

    La función es idempotente: volver a sanear el resultado no altera el valor.
    No se permiten atributos (por tanto desaparecen ``onclick``, ``style``,
    ``href``...). Las etiquetas desconocidas se desenvuelven y las peligrosas
    se eliminan junto con su contenido.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Un texto plano no necesita pasar por el parser; así se conservan los
    # acentos, ampersands y saltos de línea legados. Solo se parsea si hay una
    # etiqueta real (``<script>``, ``<b>``...); comparaciones como ``< 5`` o
    # ``<5`` no son etiquetas y se mantienen intactas.
    if not _TAG_PATTERN.search(text):
        return text
    parser = _SanitizeParser()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts).strip()


class _SanitizeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # ``attrs`` se ignora a propósito: la allowlist no admite atributos.
        del attrs
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth:
            return
        mapped = _TAG_ALIASES.get(tag, tag)
        if mapped == "br":
            self.parts.append("<br>")
            return
        if mapped in _ALLOWED_TAGS:
            self.parts.append(f"<{mapped}>")
            self.stack.append(mapped)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth:
            return
        mapped = _TAG_ALIASES.get(tag, tag)
        if mapped == "br":
            return
        if mapped not in _ALLOWED_TAGS or mapped not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.parts.append(f"</{top}>")
            if top == mapped:
                break

    def handle_data(self, data: str) -> None:
        if self.drop_depth or not data:
            return
        self.parts.append(escape(data, quote=False))

    def close(self) -> None:
        super().close()
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")


@dataclass
class RichRun:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class RichBlock:
    kind: str  # paragraph | bullet | number
    runs: list[RichRun] = field(default_factory=list)
    level: int = 0
    number: int = 0


# --- Markdown legado / pegado sin HTML -------------------------------------
# Los textos guardados antes del editor podían venir en Markdown. El DOCX debe
# interpretar sus marcas y no escribirlas como texto visible.
_MD_ESCAPABLE = set("\\`*_{}[]()#+-.!>~|")
_MD_BULLET_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:[-*+]|[•·▪◦‣∙\uf0b7])\s+(?P<text>.+?)\s*$"
)
_MD_ORDERED_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<number>\d+)\\?[.)]\s+(?P<text>.+?)\s*$"
)


def _md_indent_level(indent: str) -> int:
    spaces = indent.replace("\t", "    ")
    return min(4, len(spaces) // 2)


def _find_md_closing(
    text: str, marker: str, start: int, *, single: bool
) -> int:
    """Busca el cierre de una marca Markdown, ignorando escapes."""
    index = start
    length = len(text)
    while index < length:
        if text[index] == "\\":
            index += 2
            continue
        if text.startswith(marker, index):
            valid = True
            if single:
                if index > 0 and text[index - 1] == marker:
                    valid = False
                if index + 1 < length and text[index + 1] == marker:
                    valid = False
            else:
                if index > 0 and text[index - 1] == marker[0]:
                    valid = False
                if (
                    index + len(marker) < length
                    and text[index + len(marker)] == marker[0]
                ):
                    valid = False
            if (
                valid
                and index > start
                and not text[start].isspace()
                and not text[index - 1].isspace()
            ):
                return index
        index += 1
    return -1


def _inline_markdown_runs(
    text: str, *, bold: bool = False, italic: bool = False
) -> list[RichRun]:
    """Convierte ``**negrita**``, ``*cursiva*`` y ``***ambas***`` en runs.

    También elimina los escapes de Markdown (``1\\.`` -> ``1.``) para que no
    aparezcan barras invertidas en el Word.
    """
    runs: list[RichRun] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            runs.append(RichRun("".join(buffer), bold=bold, italic=italic))
            buffer.clear()

    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 < len(text) and text[index + 1] in _MD_ESCAPABLE:
                buffer.append(text[index + 1])
                index += 2
                continue
            if index + 1 == len(text):
                # Barra final usada como salto duro por algunos serializadores.
                index += 1
                continue
            buffer.append(char)
            index += 1
            continue

        if text.startswith("***", index) or text.startswith("___", index):
            marker = text[index : index + 3]
            end = _find_md_closing(text, marker, index + 3, single=False)
            if end != -1:
                flush()
                runs.extend(
                    _inline_markdown_runs(
                        text[index + 3 : end], bold=True, italic=True
                    )
                )
                index = end + 3
                continue

        if text.startswith("**", index) or text.startswith("__", index):
            marker = text[index : index + 2]
            end = _find_md_closing(text, marker, index + 2, single=False)
            if end != -1:
                flush()
                runs.extend(
                    _inline_markdown_runs(
                        text[index + 2 : end], bold=True, italic=italic
                    )
                )
                index = end + 2
                continue

        if char in "*_":
            if char == "_" and index > 0 and text[index - 1].isalnum():
                buffer.append(char)
                index += 1
                continue
            end = _find_md_closing(text, char, index + 1, single=True)
            if end != -1:
                flush()
                runs.extend(
                    _inline_markdown_runs(
                        text[index + 1 : end], bold=bold, italic=True
                    )
                )
                index = end + 1
                continue

        buffer.append(char)
        index += 1

    flush()
    return runs


def _lstrip_runs(runs: list[RichRun]) -> None:
    for run in runs:
        run.text = run.text.lstrip()
        if run.text:
            return


def _runs_text(runs: list[RichRun]) -> str:
    return "".join(run.text for run in runs)


def _parse_md_list_line(line: str) -> tuple[str, int, int, str] | None:
    """Devuelve ``(kind, level, number, resto)`` si la línea es un ítem."""
    bullet = _MD_BULLET_RE.match(line)
    if bullet:
        return (
            "bullet",
            _md_indent_level(bullet.group("indent")),
            0,
            bullet.group("text"),
        )
    ordered = _MD_ORDERED_RE.match(line)
    if ordered:
        return (
            "number",
            _md_indent_level(ordered.group("indent")),
            int(ordered.group("number")),
            ordered.group("text"),
        )
    return None


def _drop_run_prefix(runs: list[RichRun], count: int) -> None:
    """Elimina ``count`` caracteres del inicio de una lista de runs."""
    while runs and count > 0:
        run = runs[0]
        if len(run.text) <= count:
            count -= len(run.text)
            runs.pop(0)
        else:
            run.text = run.text[count:]
            count = 0
    _lstrip_runs(runs)


def _split_runs_newlines(runs: list[RichRun]) -> list[list[RichRun]]:
    """Divide los runs en líneas lógicas conservando su formato."""
    lines: list[list[RichRun]] = [[]]
    for run in runs:
        chunks = run.text.split("\n")
        for index, chunk in enumerate(chunks):
            if index:
                lines.append([])
            if chunk:
                lines[-1].append(RichRun(chunk, run.bold, run.italic))
    return lines


def markdown_to_blocks(text: str) -> list[RichBlock]:
    """Convierte texto plano/Markdown legado en bloques con formato."""
    blocks: list[RichBlock] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        parsed = _parse_md_list_line(line)
        if parsed is not None:
            kind, level, number, rest = parsed
            runs = _inline_markdown_runs(rest)
            if runs:
                blocks.append(RichBlock(kind, runs, level, number))
            continue
        runs = _inline_markdown_runs(line.strip())
        if runs:
            blocks.append(RichBlock("paragraph", runs))
    return blocks


class _DocxHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[RichBlock] = []
        self.current: RichBlock | None = None
        self.bold = 0
        self.italic = 0
        self.drop_depth = 0
        self.list_stack: list[list[Any]] = []
        self.li_depth = 0

    def _ensure_block(self) -> RichBlock:
        if self.current is not None:
            return self.current
        if self.list_stack:
            list_kind = self.list_stack[-1][0]
            level = len(self.list_stack) - 1
            number = 0
            if list_kind == "ol":
                self.list_stack[-1][1] += 1
                number = int(self.list_stack[-1][1])
            kind = "number" if list_kind == "ol" else "bullet"
            self.current = RichBlock(kind, [], level, number)
        else:
            self.current = RichBlock("paragraph")
        return self.current

    def _flush(self) -> None:
        block = self.current
        self.current = None
        if block is None:
            return
        runs = [run for run in block.runs if run.text]
        if not runs:
            return
        # Un párrafo con saltos puede contener una lista escrita como texto
        # (``uno<br>1. dos``). En ese caso cada línea pasa a ser su bloque.
        if not self.list_stack:
            lines = _split_runs_newlines(runs)
            if len(lines) > 1:
                parsed = [
                    _parse_md_list_line(_runs_text(line).strip())
                    for line in lines
                ]
                if any(parsed[1:]):
                    for index, (line, item) in enumerate(zip(lines, parsed)):
                        self._emit_line(
                            line, item, block if index == 0 else None
                        )
                    return
        self._trim_runs(runs)
        if not runs:
            return
        block.runs = runs
        self.blocks.append(block)

    @staticmethod
    def _trim_runs(runs: list[RichRun]) -> None:
        # Recorta espacios en los extremos del bloque, no entre runs.
        runs[0].text = runs[0].text.lstrip()
        runs[-1].text = runs[-1].text.rstrip()

    def _emit_line(
        self,
        runs: list[RichRun],
        parsed: tuple[str, int, int, str] | None,
        fallback: RichBlock | None = None,
    ) -> None:
        runs = [run for run in runs if run.text]
        if not runs:
            return
        self._trim_runs(runs)
        runs = [run for run in runs if run.text]
        if not runs:
            return
        if parsed is None:
            if fallback is None or fallback.kind == "paragraph":
                self.blocks.append(RichBlock("paragraph", runs))
            else:
                self.blocks.append(
                    RichBlock(fallback.kind, runs, fallback.level, fallback.number)
                )
            return
        kind, level, number, rest = parsed
        prefix = len(_runs_text(runs)) - len(rest)
        if prefix > 0:
            _drop_run_prefix(runs, prefix)
        if not runs:
            return
        self.blocks.append(RichBlock(kind, runs, level, number))

    def _append_text(self, data: str) -> None:
        text = re.sub(r"[ \t\r\n]+", " ", data.replace("\xa0", " "))
        if not text:
            return
        if not text.strip():
            block = self.current
            if (
                block is not None
                and block.runs
                and not block.runs[-1].text.endswith((" ", "\n"))
            ):
                block.runs.append(RichRun(" ", self.bold > 0, self.italic > 0))
            return
        at_start = not self.list_stack and (
            self.current is None
            or (self.current.kind == "paragraph" and not self.current.runs)
        )
        if at_start:
            parsed = _parse_md_list_line(text.lstrip())
            if parsed is not None:
                kind, level, number, rest = parsed
                block = self._ensure_block()
                block.kind = kind
                block.level = level
                block.number = number
                text = rest
        block = self._ensure_block()
        block.runs.extend(
            _inline_markdown_runs(
                text, bold=self.bold > 0, italic=self.italic > 0
            )
        )

    def _append_break(self) -> None:
        block = self.current
        if block is None:
            return
        if block.runs and not block.runs[-1].text.endswith("\n"):
            block.runs.append(RichRun("\n", self.bold > 0, self.italic > 0))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth:
            return
        if tag in {"p", "div"}:
            if self.li_depth:
                # Un ``<div>``/``<p>`` dentro de ``<li>`` es una línea más del
                # mismo ítem, no un bloque nuevo (así no se pierde la viñeta).
                self._append_break()
            else:
                self._flush()
                self.current = RichBlock("paragraph")
        elif tag in {"ul", "ol"}:
            self._flush()
            self.list_stack.append([tag, 0])
        elif tag == "li":
            self._flush()
            self.li_depth += 1
            list_kind = self.list_stack[-1][0] if self.list_stack else "ul"
            level = max(0, len(self.list_stack) - 1)
            number = 0
            if list_kind == "ol":
                self.list_stack[-1][1] += 1
                number = int(self.list_stack[-1][1])
            self.current = RichBlock(
                "number" if list_kind == "ol" else "bullet", [], level, number
            )
        elif tag in {"strong", "b"}:
            self.bold += 1
        elif tag in {"em", "i"}:
            self.italic += 1
        elif tag == "br":
            self._append_break()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth:
            return
        if tag in {"p", "div"}:
            if self.li_depth:
                return
            self._flush()
        elif tag == "li":
            self._flush()
            self.li_depth = max(0, self.li_depth - 1)
        elif tag in {"ul", "ol"}:
            self._flush()
            if self.list_stack:
                self.list_stack.pop()
        elif tag in {"strong", "b"}:
            self.bold = max(0, self.bold - 1)
        elif tag in {"em", "i"}:
            self.italic = max(0, self.italic - 1)

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        self._append_text(data)

    def close(self) -> None:
        super().close()
        self._flush()


def html_to_blocks(value: Any) -> list[RichBlock]:
    """Convierte HTML permitido (o texto plano) en bloques para el DOCX."""
    text = sanitize_estrategia_html(value)
    if not text:
        return []
    if not _TAG_PATTERN.search(text):
        return markdown_to_blocks(unescape(text))
    parser = _DocxHTMLParser()
    parser.feed(text)
    parser.close()
    return parser.blocks


def _add_run(paragraph, text: str, properties, *, bold: bool, italic: bool):
    run = paragraph.add_run()
    if text:
        run.text = text
    if properties is not None:
        run._r.insert(0, deepcopy(properties))
    run.bold = bold
    run.italic = italic
    run.underline = False
    return run


def _write_block(
    paragraph,
    block: RichBlock,
    *,
    properties,
    base_left_indent,
) -> None:
    if block.kind in {"bullet", "number"}:
        marker = "• " if block.kind == "bullet" else f"{block.number}. "
        if base_left_indent is None:
            left = Inches(0.5 + 0.25 * block.level)
        else:
            left = base_left_indent + Inches(0.25 * (block.level + 1))
        paragraph.paragraph_format.left_indent = left
        paragraph.paragraph_format.first_line_indent = -Inches(0.25)
        _add_run(paragraph, marker, properties, bold=False, italic=False)

    for rich_run in block.runs:
        parts = rich_run.text.split("\n")
        last_run = None
        for index, part in enumerate(parts):
            if index:
                if last_run is None:
                    last_run = _add_run(
                        paragraph,
                        "",
                        properties,
                        bold=False,
                        italic=False,
                    )
                last_run.add_break()
            if part:
                last_run = _add_run(
                    paragraph,
                    part,
                    properties,
                    bold=rich_run.bold,
                    italic=rich_run.italic,
                )


def html_to_docx_paragraphs(
    paragraph,
    value: Any,
    *,
    placeholder: str,
    prefix: str | None = None,
    body_properties=None,
) -> list[Paragraph]:
    """Reemplaza ``paragraph`` por el contenido rico y devuelve los párrafos.

    ``prefix`` se usa para el rótulo "Estrategia o Actividades llevadas a cabo:"
    de las secciones que lo llevan en la plantilla. Los textos planos históricos
    se insertan como párrafos normales.
    """
    blocks = html_to_blocks(value)
    if not blocks:
        blocks = [RichBlock("paragraph", [RichRun(placeholder)])]

    if prefix:
        if blocks[0].kind == "paragraph":
            blocks[0].runs.insert(0, RichRun(prefix, bold=True))
        else:
            blocks.insert(0, RichBlock("paragraph", [RichRun(prefix, bold=True)]))

    base_pPr = deepcopy(paragraph._p.pPr) if paragraph._p.pPr is not None else None
    if base_pPr is not None:
        for num_pr in base_pPr.findall(qn("w:numPr")):
            base_pPr.remove(num_pr)
    base_left_indent = paragraph.paragraph_format.left_indent

    created: list[Paragraph] = []
    previous_element = paragraph._p
    for index, block in enumerate(blocks):
        if index == 0:
            target = paragraph
            for child in list(target._p):
                if child.tag != qn("w:pPr"):
                    target._p.remove(child)
            if base_pPr is not None:
                current_pPr = target._p.pPr
                if current_pPr is not None:
                    target._p.remove(current_pPr)
                target._p.insert(0, deepcopy(base_pPr))
        else:
            element = OxmlElement("w:p")
            if base_pPr is not None:
                element.append(deepcopy(base_pPr))
            previous_element.addnext(element)
            target = Paragraph(element, paragraph._parent)
        _write_block(
            target,
            block,
            properties=body_properties,
            base_left_indent=base_left_indent,
        )
        created.append(target)
        previous_element = target._p
    return created


__all__ = [
    "RichBlock",
    "RichRun",
    "html_to_blocks",
    "html_to_docx_paragraphs",
    "sanitize_estrategia_html",
]
