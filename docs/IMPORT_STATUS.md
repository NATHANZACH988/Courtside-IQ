# Starter import status

Source: `courtside-iq-dual-agent-starter(1).zip` (34 files, ZIP integrity verified).

The archive was verified locally: 34 research tests and 3 website checks passed.

**GitHub status:** Collaboration foundation, .gitignore, CI workflow and this manifest are committed. **The full archive contents have not been pushed.** Do not treat local test results as CI validation of GitHub source.

To import the full package from a machine with the ZIP and GitHub credentials:

```bash
unzip 'courtside-iq-dual-agent-starter(1).zip' -d /tmp/courtside-import
cd /path/to/clone/of/Courtside-IQ
cp -R /tmp/courtside-import/courtside-iq/research ./
cp -R /tmp/courtside-import/courtside-iq/web ./
cp -R /tmp/courtside-import/courtside-iq/tests ./
cp /tmp/courtside-import/courtside-iq/docs/LAUNCH.md ./docs/
python -m unittest discover -s research/tests -p 'test_*.py' -v
python -m unittest discover -s tests -p 'test_*.py' -v
git checkout -b feat/import-starter
 git add research web tests docs/LAUNCH.md
 git commit -m 'Import validated NBA research and website starter'
 git push -u origin feat/import-starter
```

Do not overwrite `README.md`, `docs/API_CONTRACT.md`, `docs/GROK_TASK_BRIEF.md` or `docs/AGENT_COLLABORATION.md` without joint review. The additional research documentation is in `research/docs/`.
