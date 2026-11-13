# Method Trees

A method is not one `.mthds` file but a folder of files: its bundles, the template files its steps print with, its Python modules, its `METHODS.toml`. The MTHDS standard calls the set of files a method is made of its **method tree**, and Pipelex reads a method from your disk only through that tree, locally as on the hosted API. A file the tree does not hold is invisible to the method's steps, however close to the bundle it lies.

## Where a tree is rooted

What you hand Pipelex decides the tree it reads:

- **A folder**, as in `pipelex run bundle invoicing/` or `-L invoicing/`, is the method rooted at the nearest `METHODS.toml` at or above it, or at the folder itself when there is none.
- **A `.mthds` file named alone**, as in `pipelex run bundle invoicing/invoice.mthds` or `pipelex validate bundle invoicing/invoice.mthds`, is the member of the tree rooted at the nearest `METHODS.toml` at or above its folder. With no `METHODS.toml` there, its method is **that one file**: a step of the bundle naming any other file, such as a `template_file`, is refused with a message saying to run the method's folder instead, or to add a `METHODS.toml` to it. Sending a folder is always your explicit act, so a stray `.mthds` file never carries its neighbours anywhere.
- **A dependency package** is the tree rooted at the package's own directory.

## What a tree holds

A tree holds the regular files under its root, except those its membership rule keeps out:

- every file or folder whose name starts with a dot, such as `.git/`, `.venv/` or `.env`;
- `__pycache__/` and `node_modules/` folders, and any folder holding a Python virtual environment;
- a nested repository (a folder holding `.git`) and a nested package (a folder holding its own `METHODS.toml`), each a tree of its own;
- every file a `.gitignore` of the tree ignores, matched as git matches it, and every file the manifest's `[package] exclude` patterns name.

A symbolic link anywhere in the tree refuses the whole tree: a tree holds regular files only, so replace the link with the file it names, or keep it out with a `.gitignore` pattern.

The tree's `.gitignore` files are what keeps a run's outputs out of the method: every folder `pipelex run` creates for its outputs holds a `.gitignore` ignoring everything in it, and so does the folder `pipelex-agent validate bundle --graph` writes its flowchart into, so a run or a validation started from the method's own folder leaves its tree, and its digest, as they were.

## File references

A file a bundle names, such as a [`PipeDocGen`](pipes/pipe-operators/PipeDocGen.md) step's `template_file`, is a path relative to the bundle's file, written with forward slashes, and it is resolved in the bundle's tree: joined to the bundle's own place in the tree, a `..` may climb out of the bundle's folder to a file elsewhere in the tree, and the result must be a file of the tree. So a bundle in `bundles/` can name `../templates/invoice.docx`, while a path climbing above the tree's root, an absolute path, a file a `.gitignore` keeps out and a file of a nested package are all refused, each refusal naming the files by their paths in the tree. Pipelex looks the path up among the tree's files and never opens a path a bundle wrote.

## Python modules

A [`PipeFunc`](pipes/pipe-operators/PipeFunc.md) step names its function by its import path from the root of the tree, such as `funcs.totals.compute_totals` for the function `compute_totals` of `funcs/totals.py`, and its module is found among the tree's files. A run imports the tree's modules with the root first on the import path, refuses the import of a file the membership rule keeps out, such as a `.gitignore`d module, and writes no `__pycache__` into the tree. On a sandbox-hosted deployment, each call of the step receives every file of the tree except its `.mthds` files, read by the tree's digest where the call is made (see [Inside a run](#inside-a-run)).

## Library directories

A library directory, such as a `-L` directory or one of `PIPELEXPATH`, is a place methods are found rather than one method. Pipelex loads its tree, then the tree of each nested package and nested repository under it, each as a method of its own whose steps read only its own files, so every method in the directory loads. A `.mthds` file kept out by the membership rule, a hidden one, a gitignored one or one inside a virtual environment, is not loaded.

## Python packages: `requirements.txt`

A method whose own Python, such as the module of a [`PipeFunc`](pipes/pipe-operators/PipeFunc.md) step, imports a package declares it in a `requirements.txt` at the root of its tree. Only the root's file declares anything: a `requirements.txt` in a subfolder is an ordinary file of the tree. Each line of the file is blank, a comment whose first character other than a space or a tab is `#`, or exactly one [PEP 508](https://peps.python.org/pep-0508/) requirement, markers and extras included:

```text
# Reading and writing spreadsheets
pandas>=2.2,<3
openpyxl==3.1.5
tzdata; python_version >= "3.12"
```

Pipelex refuses, naming each such line, a requirement naming a URL (`name @ https://…`), an option of any kind (a line starting with `-`, such as `-r`, `-e`, `-c` or `--index-url`), a comment after a requirement on the same line, and a line continued with a backslash. A comment after a requirement is refused as a comment whatever it says, a URL in it included. The file must be UTF-8 text.

When a tree holding Python and a root `requirements.txt` loads, Pipelex checks every requirement against the Python environment its PipeFunc steps run in, before importing any of the tree's Python and before building any of its pipes, and refuses the method when one is not met, naming each requirement and why. A requirement whose marker is false in that environment is not needed there and is not checked. A tree with no Python is not checked, since nothing in it could import a package. A package your method calls by its address is checked the same way when it loads, its refusal naming the package by its address. Pipelex never installs anything.

- **Locally**, a PipeFunc runs in the interpreter Pipelex runs in, so the requirements are checked against the packages installed there, extras included. The refusal names the method's folder and gives the command that installs what is missing into that interpreter, such as `uv pip install --python /path/to/python 'pandas>=2.2,<3'`. When Pipelex was installed as a uv tool, add the packages to the tool instead, which keeps them across upgrades: `uv tool install pipelex --with 'pandas>=2.2,<3'`.
- **On a sandbox-hosted deployment**, such as the hosted API, a PipeFunc runs in the deployment's sandbox, whose packages are the whole offer: nothing is installed into a running sandbox. The requirements are checked against the packages the deployment states its sandbox offers for them, a fixed package set, or an environment the deployment builds for your method's requirements, and a method asking for a package it does not offer, or for a version it does not offer, is refused when it loads and when it is validated, naming each requirement. A deployment that can build no environment holding your requirements, such as one whose packages would conflict with a version its sandbox pins, refuses them with its own explanation. A requirement with extras cannot be checked there and is refused, so list the packages the extra brings directly.

Python declaring a structure class is refused on a sandbox-hosted deployment whatever its requirements: see [Python classes](concepts/python-classes.md).

## Where a folder's run starts

`pipelex run bundle <folder>` with no `--pipe` starts where the MTHDS protocol says a run naming no pipe starts, since the bundles of a folder have no order:

1. With a `METHODS.toml` at the tree's root, the run starts at its `main_pipe`, in the bundle of a domain exporting it that defines it. A manifest declaring no `main_pipe` is refused.
2. With no `METHODS.toml`, the run starts at the one `main_pipe` the tree's bundles declare. None, or several, is refused, the message naming each bundle by its path in the tree.

`--pipe` names the pipe to start at, as `pipe_code` or `domain.pipe_code`, and needs neither. A `.mthds` file named alone starts at its own `main_pipe`.

## Limits and the tree digest

Listing a tree reads and hashes every file in it. A local load lists each tree under this machine's own limits, set under `[interpreter.method_tree_limits]`: `max_files` (10,000 by default) and `max_total_bytes` (1 GiB by default), with `max_file_bytes`, the size of one file, unchecked unless you set it. The lister counts before it hashes anything, so a folder handed over by mistake, such as a home directory, is refused in moments, and the refusal says to run the method's own folder or to raise the limits in your project's `.pipelex/pipelex.toml`:

```toml
[interpreter.method_tree_limits]
max_files = 50000
max_total_bytes = 4294967296
```

These limits are not the hosted API's. A deployment sets its own, which a local run cannot know, and applying them locally would refuse a method rooted in a cluttered folder that loads today; a sender warned of the hosted limits before it sends is the hosted run's concern, not a local load's.

Every listing computes the tree's digest, the SHA-256 of its canonical listing of paths, hashes and sizes, which names the exact files of a method: two folders with the same files have the same digest. A local run records the digest of the tree it ran, and lists that tree once: the command lists the folder or the file it was handed to find the pipe to start at, and the run loads the tree that listing returned rather than listing it again, so the digest recorded is the digest of the tree loaded. `validate bundle` and `fix bundle` likewise load the tree they listed to resolve their target, and so does the API server, which lists a request's method once to check its requirements and to load it. `pipelex run bundle` prints the digest with the run's recap and writes `method_tree.json` into the run's output folder, holding the digest, the tree's root on this machine, its entry and each file's path, hash and size. `pipelex-agent run bundle` adds `method_tree_digest` to the run's output file and, with `--with-memory`, to its output. A run lists each tree once whichever way it is named: a folder and a symbolic link naming it are one listing, as the lister follows such a link, and a bundle file named alone inside a library directory shares the listing of the tree the directory roots, while a symbolic link to a bundle file, named alone, is refused as the lister refuses it, even after the run listed the file it points to.

The files of a tree may change after it is listed, so a run never trusts them blindly. The load reads each bundle it parses, the `requirements.txt` it judges and the Python it scans against the hash the listing recorded, and reads every file of a tree listed before the load again, once per run, as the load takes the tree, such as the folder the command resolved: a bundle, a template or any other file of the tree edited, replaced or removed since the listing is refused before anything of the method is parsed or run, with a `MethodTreeChangedError` (`method.package_invalid`, reason `tree_changed`) naming the file by its path in the tree, which `run`, `validate` and `fix` report as an invalid method whose item names that file. Run again once the files stop changing. A file a step reads during the run, such as a template, is read against its hash as well (see [Inside a run](#inside-a-run)).

## Inside a run

A run carries no file of its method. The library a run hands from step to step, its crate, names the tree each bundle belongs to by the tree's digest and the bundle by its path in the tree, and a step names a file it reads, such as a `PipeDocGen` step's template file, the same way. The files a request submits with bundles sent as text make a tree too, with those bundles at its root, named by its digest like a folder's.

Every method file is read where reading is allowed, at the moment a step uses it: a `PipeDocGen` step's template file at its print, and the files of a `PipeFunc` call where the call is made. Each read goes through the method file store, by the tree's digest and under the run's read scope, and is checked against the digest: the listing read must have that digest, and each file the hash the listing gives it. Locally, the store serves the trees the process's libraries hold, from the folder they were listed from or from the files submitted with them. A distributed orchestrator, such as Temporal, runs a step's leaves apart from the process that loaded the method, and its deployment provides the store that serves them there: the orchestrator copies every tree the run names into it while it dispatches the run, before the runner drops the files the trees were listed from.

A run records two identities of its method: the digest of its tree, which changes with any byte of any file, and the fingerprint of its crate, which changes only with the meaning of its concepts and pipes. A method whose bundles were all sent as text, with no file beside them, belongs to no tree, so its run records the fingerprint alone.
