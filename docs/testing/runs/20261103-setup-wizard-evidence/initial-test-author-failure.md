# Initial independent test run — test assertion error

Provenance: transcript output from the first `functions.exec` call running
`.local-reports/python313/python.exe -X utf8 -m pytest tests/test_setup_runtime.py -q --tb=short --basetemp C:/Temp/bsp-setup-sol`
on Windows, before the assertion correction. This is a copied excerpt from the tool result, not an original redirected log file.

```text
..s...s.......F.......................                                   [100%]
================================== FAILURES ===================================
________ test_ssh_argv_is_fixed_forwarding_without_shell_interpolation ________
tests\test_setup_runtime.py:121: in test_ssh_argv_is_fixed_forwarding_without_shell_interpolation
    assert argv[-6:] == ["-p", "2222", "-l", "operator", "linux.test"]
E   AssertionError: assert ['127.0.0.1:8... 'linux.test'] == ['-p', '2222'... 'linux.test']
E     At index 0 diff: '127.0.0.1:8771:127.0.0.1:8771' != '-p'
E     Left contains one more item: 'linux.test'
E     Use -v to get more diff
=========================== short test summary info ===========================
FAILED tests/test_setup_runtime.py::test_ssh_argv_is_fixed_forwarding_without_shell_interpolation
1 failed, 35 passed, 2 skipped, 2 warnings in 0.40s
```

The test selected six tail arguments but expected five. It was corrected to
`argv[-5:]`; no production code changed for this failure. Subsequent results
are preserved separately in `setup-runtime.txt` (44 passed, 4 skipped),
`setup-runtime-v2.txt` (45 passed, 4 skipped), and their JUnit XML files.
An intermediate unredirected rerun also reported 36 passed, 2 skipped.
