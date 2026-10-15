# Publishing and collaboration

## First push

Create an empty **public** GitHub repository named `caliptra-vck190` under your
chosen personal account or organization. Do not initialize a remote README if
the prepared local repository already has its first commit. From the prepared
repository on the workstation:

```bash
git remote add origin git@github.com:zhenghuama/caliptra-vck190.git
git push -u origin main
```

GitHub SSH credentials
must already be configured for the person pushing. Alternatively, with GitHub
CLI installed and authenticated:

```bash
gh repo create zhenghuama/caliptra-vck190 --public --source=. --remote=origin --push
```

Use one creation route, not both. See the
[official GitHub CLI reference](https://cli.github.com/manual/gh_repo_create).

## Collaborator workflow

```bash
git clone https://github.com/zhenghuama/caliptra-vck190.git
cd caliptra-vck190
git switch -c yourname/change-description
```

Read `docs/usage.md` to use the existing board. Obtain workstation/board access
separately: cloning a public repository does not grant SSH access. No FPGA build
is required for running tests on the existing installation. Coordinate one test
session at a time, and arrange reboots with other users.

For source development or a fresh setup, run `./scripts/prepare-source.sh`.
This initializes the official `upstream/caliptra-sw` submodule at the pinned
revision and creates an independent patched working copy, with the upstream
project's own nested submodules initialized there. It deliberately does not
initialize optional private modules. To inspect only the clean upstream source,
run `git submodule update --init -- upstream/caliptra-sw` instead.
Edit infrastructure directly in this repo. Caliptra changes belong in the
versioned patch or, for sustained development, a dedicated fork with committed
changes and an updated pinned revision. The generated `work/` checkout is
ignored; edits there do not automatically become part of the infrastructure
repo. Include relevant smoke-test results in a pull request. Keep generated
images and build caches outside Git; distribute tested images as separate
artifacts with hashes and provenance.

Give trusted contributors GitHub write access or accept pull requests from
their forks. Keep `main` as the reviewed baseline. Hardware-affecting changes
should identify the exact source/tool versions and whether they were tested on
the physical board.

## Optional private submodules later

From this infrastructure repo:

```bash
git submodule add git@github.com:ORG/private-project.git private/project
git add .gitmodules private/project
git commit -m "Add optional private project"
git push
```

An authorized collaborator can then initialize only that optional module:

```bash
git submodule update --init --recursive private/project
```

The public parent stores the private repo URL/path and a pinned commit ID, not
its source files. Those names and commit IDs are public. Access to the private
repository is granted independently. A blanket recursive clone will fail on
private modules for users without access, so keep the public setup independent
and initialize private modules explicitly. Never place credentials in URLs.
If even project names must remain private, use a separate private integration
repo instead. See [Git's submodule guide](https://git-scm.com/book/en/v2/Git-Tools-Submodules).
