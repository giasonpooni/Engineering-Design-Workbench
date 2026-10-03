"""Present so that packaging carries this directory at all.

`renderer/` is a browser view -- HTML, two scene files, and a vendored
three.js. None of it is importable Python, and nothing in this
distribution imports it. But a wheel installs PACKAGES, and a directory
that is not one is simply dropped: the first build of this release put
41 entries in the wheel and not one of them was under `renderer/`,
while the NOTICE that did install said the three.js notice "ships with
it". It did not.

So this file exists only in the release, not in the source tree, which
is why it lives in the template beside the licence and the README. It
makes `renderer` a package for packaging's sake; `package-data` in
`pyproject.toml` then carries the assets, and `_check_assets_are_packaged`
refuses a build whose declaration stops covering them.
"""
