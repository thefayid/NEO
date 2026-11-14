"""
core/ambient_copilot.py — Ambient HUD "Live Copilot" Lens & Proactive Error Observer for NEO.

Provides real-time semantic categorization, error sniffing, and contextual action dispatch:
1. Deep Classification:
   - STACK_TRACE: Python, Node/TS, Rust, C/C++, Go, Bash exit failures
   - SOURCE_CODE: Python, JS/TS, HTML/CSS, JSON/YAML, SQL queries
   - SQL_QUERY: Database queries (SELECT, UPDATE, INSERT, DELETE, JOIN, DDL)
   - WEB_RESOURCE: URLs, GitHub repositories, documentation links
   - NATURAL_LANGUAGE: Multilingual text, prose, prompts
   - DATA_RECORDS: CSV, tabular data, numeric series
2. Error Sniffer & Buffer:
   - Tracks recent stack traces and system failures in an in-memory buffer.
   - Enables zero-latency retrieval and autonomous self-fixing ("Neo, fix that error").
3. Contextual Action Generation:
   - Computes targeted executable actions based on semantic type.
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ContentKind(str, Enum):
    STACK_TRACE = "stack_trace"
    SOURCE_CODE = "source_code"
    SQL_QUERY = "sql_query"
    WEB_RESOURCE = "web_resource"
    NATURAL_LANGUAGE = "natural_language"
    DATA_RECORDS = "data_records"
    PLAIN_TEXT = "plain_text"


@dataclass
class CopilotAnalysis:
    kind: ContentKind
    title: str
    badge_label: str
    badge_icon: str
    badge_color: str
    preview_text: str
    raw_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    actions: List[Tuple[str, str]] = field(default_factory=list)  # [(button_label, command_template)]


class AmbientCopilotClassifier:
    """Classifies clipboard and ambient textual content into rich executable copilot intents."""

    _PYTHON_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE)
    _PYTHON_ERROR_LINE_RE = re.compile(r"^([A-Za-z0-9_.]+(?:Error|Exception|Interrupt|Exit)):\s*(.*)$", re.MULTILINE)
    _FILE_LINE_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>\w+))?')
    
    _JS_ERROR_RE = re.compile(r"(?:Uncaught\s+)?([A-Za-z0-9_]+Error):\s*(.+)")
    _JS_STACK_RE = re.compile(r"\s+at\s+(?:(?P<func>[^(\n]+)\s+\()?(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+)\)?")
    
    _RUST_PANIC_RE = re.compile(r"thread '.*' panicked at '(.*)', ([^:\n]+):(\d+):(\d+)")
    _CPP_ERROR_RE = re.compile(r"([^:\n]+):(\d+):(?:\d+:)?\s*(?:fatal\s+)?error:\s*(.+)")
    
    _SQL_KEYWORDS = ("SELECT ", "INSERT INTO ", "UPDATE ", "DELETE FROM ", "CREATE TABLE ", "ALTER TABLE ", "DROP TABLE ")

    @classmethod
    def classify(cls, text: str) -> CopilotAnalysis:
        raw = (text or "").strip()
        if not raw:
            return CopilotAnalysis(
                kind=ContentKind.PLAIN_TEXT,
                title="Empty Content",
                badge_label="EMPTY",
                badge_icon="📋",
                badge_color="#64748b",
                preview_text="",
                raw_content="",
                actions=[],
            )

        # 1. Stack Trace / Error Detection
        stack_analysis = cls._detect_stack_trace(raw)
        if stack_analysis:
            return stack_analysis

        # 2. SQL Query
        sql_analysis = cls._detect_sql_query(raw)
        if sql_analysis:
            return sql_analysis

        # 3. Web Resource / Git Repo
        web_analysis = cls._detect_web_resource(raw)
        if web_analysis:
            return web_analysis

        # 4. Source Code
        code_analysis = cls._detect_source_code(raw)
        if code_analysis:
            return code_analysis

        # 5. Data Records (CSV / Tabular / JSON)
        data_analysis = cls._detect_data_records(raw)
        if data_analysis:
            return data_analysis

        # 6. Natural Language / General Text
        return cls._detect_natural_language(raw)

    @classmethod
    def _detect_stack_trace(cls, text: str) -> Optional[CopilotAnalysis]:
        lines = text.splitlines()
        is_py_trace = bool(cls._PYTHON_TRACEBACK_RE.search(text))
        py_err_match = cls._PYTHON_ERROR_LINE_RE.search(text)
        js_err_match = cls._JS_ERROR_RE.search(text)
        rust_match = cls._RUST_PANIC_RE.search(text)
        cpp_match = cls._CPP_ERROR_RE.search(text)

        if not (is_py_trace or py_err_match or js_err_match or rust_match or cpp_match or "exit code 1" in text.lower()):
            return None

        err_type = "Runtime Error"
        err_msg = ""
        target_file = ""
        target_line = ""

        if is_py_trace:
            if py_err_match:
                err_type = py_err_match.group(1).strip()
                err_msg = py_err_match.group(2).strip()
            # Find deepest file & line
            file_matches = list(cls._FILE_LINE_RE.finditer(text))
            if file_matches:
                deepest = file_matches[-1]
                target_file = Path(deepest.group("file")).name
                target_line = deepest.group("line")
        elif cls._JS_STACK_RE.search(text) or (js_err_match and " at " in text):
            if js_err_match:
                err_type = js_err_match.group(1).strip()
                err_msg = js_err_match.group(2).strip()
            stack_matches = list(cls._JS_STACK_RE.finditer(text))
            if stack_matches:
                deepest = stack_matches[0]
                target_file = Path(deepest.group("file")).name
                target_line = deepest.group("line")
        elif rust_match:
            err_type = "Rust Panic"
            err_msg = rust_match.group(1)
            target_file = Path(rust_match.group(2)).name
            target_line = rust_match.group(3)
        elif cpp_match:
            err_type = "Compiler Error"
            target_file = Path(cpp_match.group(1)).name
            target_line = cpp_match.group(2)
            err_msg = cpp_match.group(3)
        elif py_err_match:
            err_type = py_err_match.group(1).strip()
            err_msg = py_err_match.group(2).strip()
            file_matches = list(cls._FILE_LINE_RE.finditer(text))
            if file_matches:
                deepest = file_matches[-1]
                target_file = Path(deepest.group("file")).name
                target_line = deepest.group("line")

        loc_str = f" in {target_file}:{target_line}" if target_file and target_line else ""
        title = f"{err_type}{loc_str}"
        preview = (err_msg or lines[-1])[:64]

        actions = [
            ("⚡ AUTONOMOUS FIX", "Diagnose and fix this stack trace in my project: {text}"),
            ("🔍 EXPLAIN CAUSE", "Explain what caused this error and how to resolve it: {text}"),
            ("📋 GENERATE PATCH", "Generate a precise drop-in code fix for this error: {text}"),
        ]

        return CopilotAnalysis(
            kind=ContentKind.STACK_TRACE,
            title=title,
            badge_label=err_type.upper(),
            badge_icon="⚠️",
            badge_color="#ef4444",  # Crimson red
            preview_text=preview,
            raw_content=text,
            metadata={
                "error_type": err_type,
                "error_message": err_msg,
                "file": target_file,
                "line": target_line,
            },
            actions=actions,
        )

    @classmethod
    def _detect_sql_query(cls, text: str) -> Optional[CopilotAnalysis]:
        upper = text.strip().upper()
        if any(upper.startswith(kw) for kw in cls._SQL_KEYWORDS) or ("SELECT " in upper and " FROM " in upper):
            preview = text.strip()[:60].replace("\n", " ")
            actions = [
                ("⚡ EXPLAIN QUERY", "Explain this SQL query step-by-step and show the expected output structure: {text}"),
                ("✨ OPTIMIZE", "Analyze this SQL query and suggest indexed, high-performance optimizations: {text}"),
                ("🔍 FIND BUGS", "Check this SQL query for syntax, NULL pitfalls, and logic errors: {text}"),
            ]
            return CopilotAnalysis(
                kind=ContentKind.SQL_QUERY,
                title="SQL Database Query",
                badge_label="SQL QUERY",
                badge_icon="🗄️",
                badge_color="#f59e0b",  # Amber gold
                preview_text=preview,
                raw_content=text,
                actions=actions,
            )
        return None

    @classmethod
    def _detect_web_resource(cls, text: str) -> Optional[CopilotAnalysis]:
        stripped = text.strip()
        if stripped.startswith("https://github.com/") or stripped.startswith("git@github.com:"):
            repo_name = stripped.rstrip("/").split("/")[-1].replace(".git", "")
            actions = [
                ("🌐 SUMMARIZE REPO", "Analyze this GitHub repository, its architecture and purpose: {text}"),
                ("📥 CLONE TO DESKTOP", "Clone this repository to Desktop/NeoProjects and inspect its setup: {text}"),
            ]
            return CopilotAnalysis(
                kind=ContentKind.WEB_RESOURCE,
                title=f"GitHub: {repo_name}",
                badge_label="GIT REPO",
                badge_icon="🐙",
                badge_color="#10b981",  # Emerald
                preview_text=stripped,
                raw_content=text,
                actions=actions,
            )
        elif stripped.startswith("http://") or stripped.startswith("https://"):
            domain = stripped.split("//", 1)[1].split("/", 1)[0]
            actions = [
                ("🌐 OPEN & SUMMARIZE", "Open this webpage, read its content and provide an executive summary: {text}"),
                ("📑 EXTRACT TEXT", "Extract all key text, tables and data from this URL: {text}"),
            ]
            return CopilotAnalysis(
                kind=ContentKind.WEB_RESOURCE,
                title=f"Link: {domain}",
                badge_label="WEB LINK",
                badge_icon="🌐",
                badge_color="#06b6d4",  # Cyan
                preview_text=stripped[:60],
                raw_content=text,
                actions=actions,
            )
        return None

    @classmethod
    def _detect_source_code(cls, text: str) -> Optional[CopilotAnalysis]:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return None

        # Python indicators
        py_score = sum(1 for l in lines if l.startswith(("def ", "class ", "import ", "from ", "async def ", "return ", "if __name__ ==")))
        # JS indicators
        js_score = sum(1 for l in lines if l.startswith(("const ", "let ", "function ", "import ", "export ", "console.log")))
        # HTML indicators
        html_score = sum(1 for l in lines if l.startswith(("<div", "<span", "<html", "<body", "<p", "<button", "<!DOCTYPE")))
        # Shell / CLI commands
        sh_score = sum(1 for l in lines if l.startswith(("pip install ", "npm install ", "npm i ", "git ", "docker ", "cargo ", "python ")))

        total_lines = len(lines)
        if py_score >= 1 or js_score >= 2 or html_score >= 1 or sh_score >= 1 or (total_lines >= 3 and any(l.endswith(("{", "};", ":")) for l in lines)):
            lang = "Python" if py_score >= js_score and py_score > 0 else ("JavaScript" if js_score > 0 else ("HTML/UI" if html_score > 0 else "Code"))
            actions = [
                ("🔍 EXPLAIN", "Explain what this code does in clear, concise bullet points: {text}"),
                ("✨ REFACTOR", "Refactor this code for readability, performance, and best practices: {text}"),
                ("🐛 DEBUG / REVIEW", "Review this code for edge cases, security issues, and silent bugs: {text}"),
                ("🧪 UNIT TESTS", "Write complete pytest / test suite with mocks for this code: {text}"),
            ]
            if sh_score >= 1 and total_lines <= 3:
                lang = "Shell Command"
                actions = [
                    ("⚡ RUN COMMAND", "Execute this safe command and report the output: {text}"),
                    ("🔍 EXPLAIN", "Explain what this command does before running it: {text}"),
                ]

            return CopilotAnalysis(
                kind=ContentKind.SOURCE_CODE,
                title=f"{lang} ({total_lines} lines)",
                badge_label=lang.upper(),
                badge_icon="💻",
                badge_color="#6366f1",  # Indigo
                preview_text=lines[0][:60],
                raw_content=text,
                metadata={"lang": lang, "lines": total_lines},
                actions=actions,
            )
        return None

    @classmethod
    def _detect_data_records(cls, text: str) -> Optional[CopilotAnalysis]:
        stripped = text.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            actions = [
                ("📊 ANALYZE JSON", "Analyze this JSON data structure, its fields, and schema insights: {text}"),
                ("✨ FORMAT / PRETTIFY", "Validate and format this JSON data cleanly: {text}"),
            ]
            return CopilotAnalysis(
                kind=ContentKind.DATA_RECORDS,
                title="JSON Data Structure",
                badge_label="JSON DATA",
                badge_icon="📊",
                badge_color="#8b5cf6",  # Violet
                preview_text=stripped[:60].replace("\n", " "),
                raw_content=text,
                actions=actions,
            )
        lines = stripped.splitlines()
        if len(lines) >= 3 and ("," in lines[0] or "\t" in lines[0] or "|" in lines[0]):
            actions = [
                ("📊 ANALYZE STATS", "Analyze these tabular data records, compute summary statistics, and highlight outliers: {text}"),
                ("📝 CONVERT TO JSON", "Convert this tabular/CSV data into a structured JSON array: {text}"),
            ]
            return CopilotAnalysis(
                kind=ContentKind.DATA_RECORDS,
                title=f"Tabular Records ({len(lines)} rows)",
                badge_label="DATA TABLE",
                badge_icon="📈",
                badge_color="#14b8a6",  # Teal
                preview_text=lines[0][:60],
                raw_content=text,
                actions=actions,
            )
        return None

    @classmethod
    def _detect_natural_language(cls, text: str) -> CopilotAnalysis:
        preview = text[:56].replace("\n", " ")
        if len(text) > 56:
            preview += "…"

        actions = [
            ("🌍 TRANSLATE", "Translate this text to English (or user native language): {text}"),
            ("📝 SUMMARIZE", "Summarize this into 3 actionable bullet points: {text}"),
            ("✨ POLISH", "Polish this text to sound professional, crisp and natural: {text}"),
            ("🔍 EXPLAIN", "Explain the key ideas in this passage: {text}"),
        ]

        return CopilotAnalysis(
            kind=ContentKind.NATURAL_LANGUAGE,
            title="Text Content",
            badge_label="SMART CLIPBOARD",
            badge_icon="📋",
            badge_color="#38bdf8",  # Sky blue
            preview_text=preview,
            raw_content=text,
            actions=actions,
        )


class AmbientCopilotEngine:
    """Singleton registry and memory store for ambient copilot errors and proactive suggestions."""

    _instance: Optional["AmbientCopilotEngine"] = None

    def __new__(cls) -> "AmbientCopilotEngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_engine()
        return cls._instance

    def _init_engine(self) -> None:
        self._recent_errors: deque[Dict[str, Any]] = deque(maxlen=30)
        self._last_analysis: Optional[CopilotAnalysis] = None
        self._last_seen_hash: str = ""

    def process_content(self, text: str) -> CopilotAnalysis:
        analysis = AmbientCopilotClassifier.classify(text)
        self._last_analysis = analysis

        if analysis.kind == ContentKind.STACK_TRACE:
            err_record = {
                "timestamp": time.time(),
                "time_str": time.strftime("%H:%M:%S"),
                "title": analysis.title,
                "error_type": analysis.metadata.get("error_type", "Runtime Error"),
                "file": analysis.metadata.get("file", ""),
                "line": analysis.metadata.get("line", ""),
                "raw_text": text[:1500],
            }
            self._recent_errors.append(err_record)

        return analysis

    def get_latest_error(self) -> Optional[Dict[str, Any]]:
        """Returns the most recently intercepted error/stack trace if any."""
        if self._recent_errors:
            return dict(self._recent_errors[-1])
        return None

    def get_recent_errors(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Returns up to `limit` recent error records."""
        return list(self._recent_errors)[-limit:]

    def clear_errors(self) -> None:
        self._recent_errors.clear()


# Global Singleton accessor
copilot_engine = AmbientCopilotEngine()
