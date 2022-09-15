# Poetry Relax

A Poetry plugin to remove upper version pins. 

## Motivation

By default, Poetry pins dependencies with `^x.y.z` which  constrains the versions to `>=x.y.z, <x.0.0`. 
This prevents dependencies from being upgraded to new major versions without explicit permission. 
When packages follow semantic versioning, this prevents breaking changes from reaching you. 
However, including this versioning constraint on published libraries can result in overly constrained packages. 
Once released, a library's version constraints cannot be updated. 
This means that if one of the library's dependencies releases a new major version, users of the library cannot use the new version of the dependency until a new version of the library is released — even if the release does not introduce breaking changes that would affect the library. 
For a single package, this is not often a big deal. 
However, with many packages this can result in unresolvable compatibilities between version requirements.
For a much more detailed discussion, see [this blog post](https://iscinumpy.dev/post/bound-version-constraints/).

The Poetry project has [opted](https://github.com/python-poetry/poetry/issues/3427) [not](https://github.com/python-poetry/poetry/issues/2731) to allow this behavior to be configured.
Instead, we must introduce a plugin to enable alternative behavior without tedious manual editing.


## Installation

The plugin must be installed in Poetry's environment. This requires use of the  `self` subcommand.

```bash
$ poetry self add poetry-plugin-relax
```

## Usage

Relax constraints that Poetry sets an upper version for:
```bash
$ poetry relax
```


Relax constraints and update packages:
```bash
$ poetry relax --update
```

Relax constraints and update the lock file:
```bash
$ poetry relax --lock
```

## Examples

The behavior of Poetry is quite reasonable for local development! This plugin is most useful when used in CI/CD pipelines.

### Relaxing requirements before publish

Run `poetry relax` before building and publishing package

### Relaxing requirements for testing

Run `poetry relax --update` before tests to test against the newest possible versions of packages

## Contributing

This project is managed with Poetry. Here are the basics for getting started.

Clone the repository:
```bash
$ git clone ...
$ cd poetry-plugin-relax
```

Install packages for development:
```bash
$ poetry install --group dev
```

Run the test suite:
```bash
$ pytest tests
```

Run linters before opening pull requests:
```bash
$ ./lint check .
$ ./lint fix .
```

## Frequently asked questions

> Can this plugin change the behavior of `poetry add` to relax constraints?

Not at this time. The Poetry project states that plugins must not alter the behavior of core Poetry commands.

> Does this plugin remove upper constraints I've added?

This plugin will only relax constraints specified with a caret (`^`). Upper constraints added with `<` and `<=` will not be changed.
