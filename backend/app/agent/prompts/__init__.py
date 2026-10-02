from pathlib import Path

_DIR = Path(__file__).parent


def load_prompt(name: str, **kwargs: object) -> str:
    """Reads app/agent/prompts/{name}.md and formats it. Prompts are files,
    never inline strings.
    """
    template = (_DIR / f"{name}.md").read_text()
    return template.format(**kwargs)
