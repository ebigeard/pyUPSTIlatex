import json
import click
from .document import UPSTILatexDocument


@click.group()
def main():
    """pyUPSTIlatex CLI"""


@main.command()
@click.argument("path", type=click.Path(exists=True))
def inspect(path):
    """Print metadata, commands and zones as JSON."""
    doc = UPSTILatexDocument.from_path(path)
    doc.read()
    out = {
        "metadata": doc.metadata,
        "commands": doc.get_commands(),
        "zones": {k: doc.get_zone(k) for k in doc.list_zones()},
    }
    click.echo(json.dumps(out, indent=2, ensure_ascii=False))


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("zone", type=str)
@click.option("--stdout/--no-stdout", default=True)
@click.option("--output", "-o", type=click.Path(), default=None)
def extract_zone(path, zone, stdout, output):
    """Extract a named zone. Writes to stdout or file."""
    doc = UPSTILatexDocument.from_path(path)
    content = doc.get_zone(zone)
    if content is None:
        raise click.ClickException(f"Zone '{zone}' not found in {path}")
    if stdout:
        click.echo(content)
    elif output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Wrote {output}")


if __name__ == "__main__":
    main()
