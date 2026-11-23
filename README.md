# BSP company handoff

Download this branch as a ZIP and extract it. The [company handoff folder](company-handoff-8abe926/) contains the complete copy-ready plugin, both prebuilt UIs, the Windows board connector, and the company assessment, porting, and independent review guides.

The package is pinned to source commit [8abe926](https://github.com/graycoral/bsp_os_upgrade_dashboard/commit/8abe9262716cbcfc287a535094f4fbd940601113). The local packaging gate passed. Company and hardware acceptance are pending.

From the extracted archive root, verify the package with Python 3.11 or later.

```sh
cd company-handoff-8abe926/bsp-plugin-copy-ready-20261122-8abe926
python3 -IB plugin.py verify . --pristine
```

Then open [00_START_HERE.md](company-handoff-8abe926/00_START_HERE.md) and begin with the [04 company assessment](company-handoff-8abe926/04_CLAUDE_OPUS_COMPANY_ASSESSMENT.md). See the [copy-ready results](company-handoff-8abe926/COPY_READY_RESULT.md) for manifest checksums and test evidence. The later [PORT-015 SSH profile change](https://github.com/graycoral/bsp_os_upgrade_dashboard/blob/557b7d070a195c44f17bf2eb05e0d8fd0dd7c73d/docs/porting/PORT-015.md) is outside this source pin.
