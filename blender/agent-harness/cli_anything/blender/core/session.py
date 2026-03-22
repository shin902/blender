"""Session management with undo/redo for cli-anything-blender."""

from copy import deepcopy
from typing import Any


MAX_HISTORY = 50


class Session:
    """Manages project state with undo/redo support.

    Keeps a deep-copy stack of up to MAX_HISTORY states.
    """

    def __init__(self, project: dict[str, Any] | None = None):
        self._stack: list[dict[str, Any]] = []
        self._index: int = -1
        self.path: str | None = None

        if project is not None:
            self.push(project)

    @property
    def project(self) -> dict[str, Any] | None:
        """Current project state, or None if no project loaded."""
        if self._index < 0:
            return None
        return self._stack[self._index]

    @property
    def modified(self) -> bool:
        """True if there are unsaved changes (more than one history entry)."""
        return self._index > 0

    def push(self, project: dict[str, Any]) -> None:
        """Push a new state onto the undo stack.

        Truncates any redo history beyond the current index.
        Trims stack to MAX_HISTORY entries.

        Args:
            project: New project state (deep-copied).
        """
        # Truncate redo history
        self._stack = self._stack[: self._index + 1]
        # Deep copy to snapshot
        self._stack.append(deepcopy(project))
        self._index = len(self._stack) - 1

        # Trim history
        if len(self._stack) > MAX_HISTORY:
            excess = len(self._stack) - MAX_HISTORY
            self._stack = self._stack[excess:]
            self._index = len(self._stack) - 1

    def undo(self) -> dict[str, Any] | None:
        """Undo to the previous state.

        Returns:
            The previous project state, or None if at the beginning.
        """
        if self._index <= 0:
            return None
        self._index -= 1
        return self.project

    def redo(self) -> dict[str, Any] | None:
        """Redo to the next state.

        Returns:
            The next project state, or None if at the end.
        """
        if self._index >= len(self._stack) - 1:
            return None
        self._index += 1
        return self.project

    def can_undo(self) -> bool:
        """True if undo is available."""
        return self._index > 0

    def can_redo(self) -> bool:
        """True if redo is available."""
        return self._index < len(self._stack) - 1

    def history_depth(self) -> int:
        """Number of states in the history stack."""
        return len(self._stack)

    def clear(self) -> None:
        """Clear all history."""
        self._stack = []
        self._index = -1
        self.path = None

    def status(self) -> dict[str, Any]:
        """Return a status summary dict."""
        return {
            "has_project": self.project is not None,
            "project_name": self.project.get("name", "") if self.project else "",
            "path": self.path or "",
            "modified": self.modified,
            "can_undo": self.can_undo(),
            "can_redo": self.can_redo(),
            "history_depth": self.history_depth(),
        }
