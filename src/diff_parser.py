import re
from typing import List, Tuple, Dict, Any, Optional
from pydantic import BaseModel, Field


# Patterns and extensions to ignore during architectural compliance review
IGNORED_EXTENSIONS = {
    # Lockfiles
    ".lock", ".lockb",
    # Images and media
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff",
    ".mp3", ".mp4", ".wav", ".avi",
    # Compiled / Binary artifacts
    ".class", ".dex", ".jar", ".aar", ".apk", ".aab", ".so", ".dylib", ".dll", ".exe",
    ".o", ".obj", ".pyc", ".pyo",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Minified assets
    ".min.js", ".min.css",
    # Compressed archives
    ".zip", ".tar", ".gz", ".bz2", ".7z",
}

IGNORED_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "gradle.lockfile",
    "Gemfile.lock",
    "composer.lock",
}

IGNORED_PATH_PREFIXES = (
    "build/",
    ".gradle/",
    ".idea/",
    ".git/",
    "gradle/wrapper/",
    "bin/",
    "out/",
    "dist/",
    "node_modules/",
    ".venv/",
    "venv/",
)


class ParsedFileDiff(BaseModel):
    """Represents the parsed diff of a single file in a Git diff."""
    file_path: str = Field(description="The primary target file path.")
    old_path: Optional[str] = Field(default=None, description="Previous file path if renamed.")
    is_new: bool = Field(default=False)
    is_deleted: bool = Field(default=False)
    is_binary: bool = Field(default=False)
    patch: str = Field(default="", description="The hunk diff text for this file.")
    line_count: int = Field(default=0, description="Total lines in this file's patch.")


def is_ignored_file(file_path: str) -> Tuple[bool, str]:
    """
    Check if a file should be ignored from architectural evaluation.
    Returns (is_ignored, reason).
    """
    normalized = file_path.replace("\\", "/").strip().lstrip("/")
    filename = normalized.split("/")[-1].lower()

    if filename in IGNORED_FILENAMES:
        return True, f"Excluded lockfile ({filename})"

    for prefix in IGNORED_PATH_PREFIXES:
        if normalized.startswith(prefix) or f"/{prefix}" in normalized:
            return True, f"Excluded build/cache path ({prefix})"

    for ext in IGNORED_EXTENSIONS:
        if filename.endswith(ext):
            return True, f"Excluded binary/media extension ({ext})"

    return False, ""


def split_raw_diff(raw_diff: str) -> List[str]:
    """
    Split a raw multi-file git diff into individual file diff sections.
    """
    if not raw_diff or not raw_diff.strip():
        return []

    # Match lines starting with 'diff --git '
    diff_sections = re.split(r"(?=^diff --git )", raw_diff, flags=re.MULTILINE)
    return [sec.strip() for sec in diff_sections if sec.strip()]


def parse_file_diff(file_diff_str: str) -> Optional[ParsedFileDiff]:
    """
    Parse a single file's git diff chunk into a structured ParsedFileDiff.
    """
    lines = file_diff_str.splitlines()
    if not lines:
        return None

    first_line = lines[0]
    file_path = ""
    old_path = None
    is_new = False
    is_deleted = False
    is_binary = False

    # Extract paths from 'diff --git a/... b/...'
    git_header_match = re.match(r"^diff --git\s+a/(.+?)\s+b/(.+)$", first_line)
    if git_header_match:
        old_path = git_header_match.group(1)
        file_path = git_header_match.group(2)
    else:
        # Fallback if diff format differs
        for line in lines:
            if line.startswith("+++ b/"):
                file_path = line[6:].strip()
                break
            elif line.startswith("--- a/") and not file_path:
                file_path = line[6:].strip()

    if not file_path:
        return None

    # Check headers for creation/deletion/binary markers
    for line in lines[:10]:
        if line.startswith("new file mode"):
            is_new = True
        elif line.startswith("deleted file mode"):
            is_deleted = True
        elif "Binary files" in line or "GIT binary patch" in line:
            is_binary = True

    return ParsedFileDiff(
        file_path=file_path,
        old_path=old_path if old_path != file_path else None,
        is_new=is_new,
        is_deleted=is_deleted,
        is_binary=is_binary,
        patch=file_diff_str,
        line_count=len(lines),
    )


def filter_and_parse_diff(raw_diff: str) -> Tuple[List[ParsedFileDiff], List[Dict[str, str]]]:
    """
    Parses a complete git diff and separates actionable code files from ignored/filtered files.
    Returns:
        (valid_files, ignored_files)
    """
    sections = split_raw_diff(raw_diff)
    valid_files: List[ParsedFileDiff] = []
    ignored_files: List[Dict[str, str]] = []

    for section in sections:
        parsed = parse_file_diff(section)
        if not parsed:
            continue

        if parsed.is_binary:
            ignored_files.append({"file": parsed.file_path, "reason": "Binary file"})
            continue

        ignored, reason = is_ignored_file(parsed.file_path)
        if ignored:
            ignored_files.append({"file": parsed.file_path, "reason": reason})
            continue

        valid_files.append(parsed)

    return valid_files, ignored_files


def chunk_files_for_review(files: List[ParsedFileDiff], max_lines_per_chunk: int = 1200) -> List[List[ParsedFileDiff]]:
    """
    Groups files into chunks so that very large MRs don't exceed model context
    or degrade attention.
    """
    chunks: List[List[ParsedFileDiff]] = []
    current_chunk: List[ParsedFileDiff] = []
    current_lines = 0

    for f in files:
        if current_chunk and (current_lines + f.line_count > max_lines_per_chunk):
            chunks.append(current_chunk)
            current_chunk = [f]
            current_lines = f.line_count
        else:
            current_chunk.append(f)
            current_lines += f.line_count

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

