"""Importing this package registers every tool (the @register_tool decorator
runs on import) - anything that needs the tool registry populated should
import app.tools, not just app.tools.registry.
"""

from app.tools import orders, transactions  # noqa: F401
