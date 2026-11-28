"""Resolve CLI output against the caller's project and the delivered source."""
import os
from pathlib import Path
import subprocess


def project_directory(project=None, project_root=None):
    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    if project:
        candidate = Path(project).expanduser()
        if candidate.is_absolute() or project.startswith(('./', '../', '~')) or candidate.is_dir():
            return candidate.resolve()
    try:
        repo = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if repo.returncode == 0:
            return Path(repo.stdout.strip()).resolve()
    except FileNotFoundError:
        pass
    return Path.cwd().resolve()


def external_output(path, source, *, project=None, project_root=None, additional_roots=()):
    source = Path(source).resolve()
    roots = [project_directory(project, project_root), source, *additional_roots]
    if (source.parent / 'PLUGIN_PACKAGE.json').is_file():
        roots.append(source.parent)
    provided = Path(path).expanduser().absolute()
    destination = provided.resolve()
    lexical = Path(os.path.normpath(provided))
    if provided.is_symlink() or any(
        candidate.is_relative_to(Path(root).resolve())
        for candidate in (lexical, destination) for root in roots
    ):
        raise ValueError('Output must be outside the project, package and source directories')
    return destination
