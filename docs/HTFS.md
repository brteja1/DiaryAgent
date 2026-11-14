# Bundled HTFS dependency

HTFS is mandatory under user decision D-07. Source: [brteja1/HTFS](https://github.com/brteja1/HTFS), MIT licensed. The repository carries it at `deps/HTFS` as a Git submodule, initially pinned to `fa82438b63e6b9daa146cd05812b062b0beffd7c` (Fix local tagfs package import). The parent repository's gitlink is the authoritative pin.

From the Diary Agent repository root:

```bash
git submodule update --init --recursive
python -m pip install -r requirements.txt
```

Use an activated virtual environment when appropriate. `make deps` runs both steps; `make PYTHON=/path/to/venv/bin/python deps` selects an interpreter. A new clone can use `git clone --recurse-submodules <repository-url>`.

The dependency installs from local source (`-e ./deps/HTFS`), with `rdflib` declared by HTFS. The optional HTFS filesystem daemon is not required. Runtime uses the bundled Python package through `HTFSAdapter`, not a `tagfs` executable. Backend origin checks prevent silently using a previously imported external HTFS package.

Config requires only `diary_path`; `llm_model` is optional. Legacy `htfs_path` keys and `DIARY_AGENT_HTFS_PATH` are ignored. Model/UI availability is independent of mandatory HTFS availability.

Every operational CLI invocation checks importability, initializes the diary's HTFS metadata if absent, and reads its tag inventory before dispatch. A missing submodule, missing Python dependency or inaccessible/broken boundary is an error before diary content writes. No command silently switches to a tag-free mode. `--help` remains available without initialization. `.tagfs.db` and `.tagfs.ttl` stay in the configured diary directory, outside the submodule.

Verify integration:

```bash
git submodule status deps/HTFS
python -c 'from diary_agent_app.htfs_adapter import HTFSAdapter; print(HTFSAdapter.require_backend())'
pytest -q tests/test_diary_agent.py
```

Tests exercise the bundled import, ignored external path settings, mandatory startup failure, and persistent resource tagging/querying in temporary diary boundaries. `pytest.ini` limits normal collection to Diary Agent tests. `make clean` excludes Git metadata and dependencies; it must not delete files from the pinned HTFS checkout.

Submodule updates are explicit maintenance changes: review the new upstream revision, update the gitlink, and rerun integration tests. Do not modify or copy another checkout's uncommitted files to manufacture a pin. Later backend failures can still occur after Markdown persistence. D-08 is now decided but not implemented: retain written content, report partial/uncertain outcomes, preserve recovery information and retry metadata without duplicating diary content. See PERSIST-01–05 in [Specification.md](Specification.md); do not infer atomicity from startup preflight.
