# Install the Ralph command-line tool

Use Python 3.11 or newer, Git, and the model client or compatible HTTP endpoint you
choose. Excubitor itself uses only Python's standard library. Model accounts and
clients are set up separately; installing Excubitor does not copy credentials,
register hooks or change client settings.

This branch is a development candidate. The new Ralph workflow has not been
published as a release. Install a reviewed wheel from this source when evaluating
it. Do not assume an older package from an index contains the same commands.

## Build once, install normally

From a reviewed source checkout:

```text
python packaging/build.py wheel --outdir dist
```

The output is `dist/excubitor-VERSION-py3-none-any.whl`, where VERSION is the package
version printed in the filename. The standard `python -m build` frontend is also
supported when its build dependencies are installed.

For a command available from your terminal, use [pipx](https://github.com/pypa/pipx#install-pipx)
and the actual wheel path:

```text
pipx install /absolute/path/to/excubitor-VERSION-py3-none-any.whl
excubitor ralph --help
```

On Windows the wheel path can be `C:\Downloads\excubitor-VERSION-py3-none-any.whl`.
Quote any path containing spaces. Pipx keeps the package in its own environment.
If the command directory is not already on PATH, follow pipx's setup instructions
and reopen the terminal. This is ordinary CLI discovery, not agent-hook registration.

## Virtual-environment alternative

A virtual environment works without pipx or a global PATH change. Create it outside
the source checkout and use its explicit commands. On Windows:

```powershell
py -3 -m venv C:\Tools\excubitor-env
C:\Tools\excubitor-env\Scripts\python.exe -m pip install --no-index C:\Downloads\excubitor-VERSION-py3-none-any.whl
C:\Tools\excubitor-env\Scripts\excubitor.exe ralph --help
```

On Linux or macOS:

```sh
python3 -m venv "$HOME/.local/share/excubitor-env"
"$HOME/.local/share/excubitor-env/bin/python" -m pip install --no-index /absolute/path/to/excubitor-VERSION-py3-none-any.whl
"$HOME/.local/share/excubitor-env/bin/excubitor" ralph --help
```

Check `python --version` for the interpreter you choose. Examples need Python 3.11+
even if a system's default `python3` is older. Neither environment activation nor
running from the source tree is required.

## Upgrade, rollback and uninstall

Finish or explicitly stop active jobs before replacing the installed package. Keep
the previous wheel and all job directories. Saved jobs bind their original settings,
checks and limits; an upgrade cannot replenish those limits or rewrite an agreement.

For pipx, install the reviewed replacement wheel with `pipx install --force` and its
path. For a virtual environment, use that environment's Python:

```text
python -m pip install --no-index --upgrade --force-reinstall /absolute/path/to/excubitor-VERSION-py3-none-any.whl
```

Use the prior reviewed wheel in the same command to roll back the package. A
rollback is not a promise that an older package understands a newer job format;
inspect its compatibility before resuming. For same-version development wheels,
`--force-reinstall` ensures the changed bytes actually replace the previous build.

Use `pipx uninstall excubitor`, or the environment's `python -m pip uninstall excubitor`.
Uninstalling removes the package and console command. It does not stop an already
running process, delete project/candidate/evidence directories, revoke model logins,
or remove separately installed legacy hooks. Stop jobs first and preserve their
reports. No cleanup of project work is part of package installation or removal.

Then follow the [Ralph quickstart](ralph-quickstart.md). Acceptance tests should exist
and prove the requested behavior before planning; setup cannot invent what counts
as success for your project.
