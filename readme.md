# Package Control Default Channel

## Submitting your package

- Fork this repository.
- Add the details of your package, in alphabetical order,
  to the correct JSON file in the [repository directory][repodir].
- Check the full [guide to submitting packages][guide] for more information.
- Create a PR and make sure you check [all the boxes][prtemplate].

[repodir]: https://github.com/wbond/package_control_channel/tree/master/repository
[guide]: https://docs.sublimetext.io/guide/package-control/submitting.html
[prtemplate]: https://github.com/wbond/package_control_channel/blob/master/.github/PULL_REQUEST_TEMPLATE.md


## About

The `channel.json`, `repository.json` and `repository/*.json` files
contain lists of repositories and packages for use with
[Package Control](https://packagecontrol.io).
These source files are processed by a crawler
and compiled into a single file:
[channel_v3.json](https://packagecontrol.io/channel_v3.json).
This is the source of all package available for installation via Package Control.

Libraries (previously named "dependencies") have their own registry at https://github.com/packagecontrol/channel.



## Other notable repositories

This is the main repository of Sublime Text packages. However:

- Linter packages should in most cases be submitted over at [SublimeLinter](https://github.com/SublimeLinter/package_control_channel).
- Similarly, any language server protocol packages are managed via [SublimeLSP](https://github.com/sublimelsp/repository).
