import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


class EnrichedFileContext(BaseModel):
    """
    Language-agnostic architectural metadata and expanded context
    extracted from the source file surrounding a diff hunk.
    """
    file_path: str
    file_extension: str
    directory_hierarchy: List[str] = Field(default_factory=list)
    package_or_namespace: str = ""
    file_imports: List[str] = Field(default_factory=list)
    enclosing_declarations: List[str] = Field(default_factory=list)
    file_structure_outline: List[str] = Field(default_factory=list)
    full_content_available: bool = False
    context_summary: str = Field(default="", description="Compact, LLM-ready context block")


def parse_universal_file_header(lines: List[str]) -> Tuple[str, List[str]]:
    """
    Language-agnostic parser to extract package/namespace/module declaration
    and all external import/using/require statements from the top of any source file.
    Works for Kotlin, Java, Swift, Python, TypeScript, Go, C#, Rust, PHP, etc.
    """
    package_or_namespace = ""
    imports: List[str] = []

    # Matches package, namespace, module
    pkg_pattern = re.compile(r"^\s*(?:package|namespace|module)\s+([A-Za-z0-9_\.\:]+)", re.IGNORECASE)
    # Matches import, using, from ... import, require, include, use
    import_pattern = re.compile(
        r"^\s*(?:import|using|use|require|include|from\s+[\w\.]+\s+import)\s+([^\n;]+)",
        re.IGNORECASE
    )

    for line in lines[:80]:
        trimmed = line.strip()
        if not trimmed or trimmed.startswith(("//", "#", "/*", "*", "<!--")):
            continue

        pkg_match = pkg_pattern.match(trimmed)
        if pkg_match and not package_or_namespace:
            package_or_namespace = pkg_match.group(1).rstrip(";").strip()
            continue

        import_match = import_pattern.match(trimmed)
        if import_match:
            imp_val = trimmed.rstrip(";").strip()
            if imp_val not in imports:
                imports.append(imp_val)
            continue

        # If we hit an actual class/type/function declaration, stop scanning header
        if re.match(r"^\s*(?:public\s+|private\s+|internal\s+|open\s+|data\s+|final\s+)*(?:class|struct|interface|enum|type|def|func|fn)\b", trimmed, re.IGNORECASE):
            break

    return package_or_namespace, imports


def extract_file_outline(lines: List[str]) -> List[str]:
    """
    Extracts high-level type and method signatures declared in the file
    without language-specific AST bindings.
    """
    outline: List[str] = []
    decl_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|internal|open|data|abstract|sealed|final|async|override)\s+)*"
        r"(class|interface|struct|protocol|enum|type|trait|service)\s+"
        r"([A-Za-z0-9_]+(?:\s*(?:<[^>]+>)?\s*(?::|extends|implements)\s*[^{]+)?)",
        re.MULTILINE
    )

    for line in lines:
        trimmed = line.strip()
        match = decl_pattern.match(trimmed)
        if match:
            clean_decl = re.sub(r"\s+", " ", match.group(0).rstrip("{").strip())
            if clean_decl not in outline:
                outline.append(clean_decl)

    return outline


def find_enclosing_scopes_for_line(lines: List[str], target_line_no: int) -> List[str]:
    """
    Language-agnostic backwards scan to locate the enclosing class/struct/function
    that contains a modified line number.
    """
    enclosing: List[str] = []
    if target_line_no <= 0 or target_line_no > len(lines):
        return enclosing

    scope_decl_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|internal|open|data|abstract|sealed|final|async|override)\s+)*"
        r"(class|interface|struct|protocol|enum|type|trait|def|func|fn|function|fun)\s+"
        r"([A-Za-z0-9_]+(?:\s*[:<(][^{:]+)?)",
        re.IGNORECASE
    )

    current_indent = float("inf")
    # Scan upwards from target line to find enclosing parent declarations
    for idx in range(min(target_line_no - 1, len(lines) - 1), -1, -1):
        line = lines[idx]
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "#", "/*", "*")):
            continue

        indent = len(line) - len(line.lstrip())
        match = scope_decl_pattern.match(stripped)
        if match and indent < current_indent:
            clean_decl = re.sub(r"\s+", " ", match.group(0).rstrip("{").strip())
            enclosing.append(clean_decl)
            current_indent = indent
            if current_indent == 0:
                break

    enclosing.reverse()
    return enclosing


def enrich_file_context(
    file_path: str,
    patch_text: str,
    project_root: Optional[Path] = None,
    hunk_start_line: Optional[int] = None
) -> EnrichedFileContext:
    """
    Produces a Smart Expanded Context for a diff hunk.
    Loads surrounding file context from disk or git workspace, extracting:
    - Path and directory hierarchy
    - Package / module / namespace
    - Active file imports and dependencies
    - Declared classes / structs and supertypes
    - Enclosing scope around modified lines
    """
    path_obj = Path(file_path)
    extension = path_obj.suffix.lower()
    directories = [p for p in path_obj.parent.parts if p not in [".", ""]]

    full_source: Optional[str] = None
    candidates = []
    if project_root:
        candidates.append(project_root / file_path)
    candidates.append(Path(file_path))

    for candidate in candidates:
        if candidate.is_file():
            try:
                full_source = candidate.read_text(encoding="utf-8", errors="replace")
                break
            except Exception:
                pass

    if full_source:
        lines = full_source.splitlines()
        package_or_ns, file_imports = parse_universal_file_header(lines)
        outline = extract_file_outline(lines)

        # If a hunk line number was detected or provided, find its enclosing scope
        target_line = hunk_start_line or 1
        if not hunk_start_line:
            # Try to extract from hunk header @@ -a,b +start,count @@
            hunk_match = re.search(r"@@\s+-\d+(?:,\d+)?\s+\+(\d+)", patch_text)
            if hunk_match:
                target_line = int(hunk_match.group(1))

        enclosing = find_enclosing_scopes_for_line(lines, target_line)
        full_available = True
    else:
        # Fallback: extract context from the diff patch text itself
        lines = patch_text.splitlines()
        clean_lines = [l[1:] if l.startswith(("+", "-", " ")) else l for l in lines]
        package_or_ns, file_imports = parse_universal_file_header(clean_lines)
        outline = extract_file_outline(clean_lines)
        enclosing = []
        full_available = False

    # Format a concise, high-signal context summary for the LLM
    summary_parts = [
        f"File: {file_path}",
        f"Path Segments: {' / '.join(directories) if directories else 'root'}",
    ]
    if package_or_ns:
        summary_parts.append(f"Namespace/Package: {package_or_ns}")
    if enclosing:
        summary_parts.append(f"Enclosing Scope: {' -> '.join(enclosing)}")
    if outline:
        summary_parts.append(f"Declared Types: {'; '.join(outline[:5])}")
    if file_imports:
        summary_parts.append(f"Imports/Dependencies ({len(file_imports)}): {', '.join(file_imports[:10])}{'...' if len(file_imports) > 10 else ''}")

    context_summary = "\n".join(f"  • {part}" for part in summary_parts)

    return EnrichedFileContext(
        file_path=file_path,
        file_extension=extension,
        directory_hierarchy=directories,
        package_or_namespace=package_or_ns,
        file_imports=file_imports,
        enclosing_declarations=enclosing,
        file_structure_outline=outline,
        full_content_available=full_available,
        context_summary=context_summary,
    )

