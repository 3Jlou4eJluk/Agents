"""
Operating System tools for file operations and shell commands.
Similar to Claude Desktop capabilities.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional
from langchain_core.tools import tool


@tool
def execute_shell_command(command: str, working_dir: Optional[str] = None) -> str:
    """
    Execute a shell command and return its output.

    Args:
        command: The shell command to execute
        working_dir: Optional working directory for the command

    Returns:
        Command output or error message
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_dir
        )

        output = f"Exit code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


@tool
def read_file(file_path: str, line_start: Optional[int] = None, line_end: Optional[int] = None) -> str:
    """
    Read contents of a file, optionally specifying line range.

    Args:
        file_path: Path to the file to read
        line_start: Optional starting line number (1-indexed)
        line_end: Optional ending line number (inclusive)

    Returns:
        File contents or error message
    """
    try:
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            return f"Error: File not found: {file_path}"

        if not path.is_file():
            return f"Error: Path is not a file: {file_path}"

        with open(path, 'r', encoding='utf-8') as f:
            if line_start is not None or line_end is not None:
                lines = f.readlines()
                start = (line_start - 1) if line_start else 0
                end = line_end if line_end else len(lines)
                content = ''.join(lines[start:end])
            else:
                content = f.read()

        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def write_file(file_path: str, content: str, mode: str = "w") -> str:
    """
    Write content to a file.

    Args:
        file_path: Path to the file to write
        content: Content to write
        mode: Write mode - "w" for overwrite, "a" for append

    Returns:
        Success message or error
    """
    try:
        path = Path(file_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, mode, encoding='utf-8') as f:
            f.write(content)

        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool
def list_directory(directory_path: str, recursive: bool = False, pattern: Optional[str] = None) -> str:
    """
    List contents of a directory.

    Args:
        directory_path: Path to the directory
        recursive: Whether to list recursively
        pattern: Optional glob pattern (e.g., "*.py")

    Returns:
        Directory listing or error message
    """
    try:
        path = Path(directory_path).expanduser().resolve()

        if not path.exists():
            return f"Error: Directory not found: {directory_path}"

        if not path.is_dir():
            return f"Error: Path is not a directory: {directory_path}"

        if recursive:
            if pattern:
                files = list(path.rglob(pattern))
            else:
                files = list(path.rglob("*"))
        else:
            if pattern:
                files = list(path.glob(pattern))
            else:
                files = list(path.iterdir())

        files.sort()

        output = f"Contents of {directory_path}:\n"
        for file in files:
            rel_path = file.relative_to(path) if recursive else file.name
            file_type = "DIR" if file.is_dir() else "FILE"
            size = file.stat().st_size if file.is_file() else "-"
            output += f"{file_type:5} {size:>10} {rel_path}\n"

        return output
    except Exception as e:
        return f"Error listing directory: {str(e)}"


@tool
def search_files(directory: str, query: str, file_pattern: str = "*") -> str:
    """
    Search for text in files within a directory.

    Args:
        directory: Directory to search in
        query: Text to search for
        file_pattern: Glob pattern for files (e.g., "*.py")

    Returns:
        Search results or error message
    """
    try:
        path = Path(directory).expanduser().resolve()

        if not path.exists() or not path.is_dir():
            return f"Error: Invalid directory: {directory}"

        results = []
        for file_path in path.rglob(file_pattern):
            if not file_path.is_file():
                continue

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            rel_path = file_path.relative_to(path)
                            results.append(f"{rel_path}:{line_num}: {line.strip()}")
            except Exception:
                continue

        if not results:
            return f"No matches found for '{query}' in {directory}"

        return f"Found {len(results)} matches:\n" + "\n".join(results[:50])
    except Exception as e:
        return f"Error searching files: {str(e)}"


def get_all_os_tools() -> List:
    """Get all OS tools as a list."""
    return [
        execute_shell_command,
        read_file,
        write_file,
        list_directory,
        search_files,
    ]
