# Adding packages to the Package Control channel

A human will be reviewing the package and assess both the quality of the package itself and the ability and willingness of the human author of the package to maintain it long term.

## PR instructions

- Title format: Add \<package name\>

### Do
- Use the template in .github/PULL_REQUEST_TEMPLATE.md.
- Provide the requested information, but no more.
- Follow the indentation and overall formatting of the existing JSON files.
- Insert the new package in alphabetical order.
- If in trouble, use the formatter under `tools/` (see `tools/README.md`).
- Refer to https://docs.sublimetext.io/guide/package-control/submitting.html for more details.

### Do not
- Do not provide information that can be seen when looking at the package repository and reading its README.
- Do not reformat the the existing JSON files, just add the entry for the new package.
