"""HTML dashboard rendering."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from aios.reports.models import PresentationContext, context_to_dict


def write_dashboard_html(
    context: PresentationContext,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    template_dir = Path(__file__).parent / "templates"
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("dashboard.html.j2")
    path.write_text(
        template.render(signal=context_to_dict(context)),
        encoding="utf-8",
    )
    return path
