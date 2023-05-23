<p align="center">
    <a href="https://pypi.python.org/pypi/poetry-relax/" alt="Latest version">
        <img alt="Latest version" src="https://img.shields.io/pypi/v/poetry-relax?style=flat-square">
    </a>
    <a href="https://devguide.python.org/versions/" alt="Supported Python versions">
        <img alt="Supported Python versions" src="https://img.shields.io/pypi/pyversions/poetry-relax?style=flat-square">
    </a>
    <a href="https://github.com/madkinsz/poetry-relax/actions/workflows/test.yaml?query=branch%3Amain" alt="Test status">
        <img alt="Test status" src="https://img.shields.io/github/actions/workflow/status/madkinsz/poetry-relax/test.yaml?label=test&style=flat-square">
    </a>
    <a href="https://github.com/madkinsz/poetry-relax/actions/workflows/build.yaml?query=branch%3Amain" alt="Build status">
        <img alt="Build status" src="https://img.shields.io/github/actions/workflow/status/madkinsz/poetry-relax/build.yaml?label=build&style=flat-square">
    </a>
</p>

# poetry-relax

A [Poetry](https://github.com/python-poetry/poetry) plugin to relax dependency versions when publishing libraries. Relax your project's dependencies from `foobar^2.0.0` to `foobar>=2.0.0`.

By default, Poetry uses caret constraints which would limit `foobar` versions to `<3.0`.
**poetry-relax**  removes these upper version bounds, allowing dependencies to be upgraded.

Removing upper version bounds is important when publishing libraries.
When searching for versions of dependencies to install, the resolver (e.g. `pip`) must respect the bounds your library specifies.
When a new version of the dependency is released, consumers of your library _cannot_ install it unless a new version of your library is also released.

It is not feasible to release patches for every previous version of most libraries, which forces users to use the most recent version of the library or be stuck without the new version of the dependency.
When many libraries contain upper version bounds, the dependencies can easily become _unsolvable_ — where libraries have incompatible dependency version requirements.
By removing upper version bounds from your library, control is returned to the user.

Poetry's default behavior is to include upper version bounds. Many people have spoken up against this style of dependency management in the Python ecosystem, including members of the Python core development team. See [the bottom of the readme](#references) for links and additional context.

Since the Poetry project will not allow this behavior to be configured, maintainers have resorted to manual editing of dependency constraints after adding. **poetry-relax** aims to automate and simplify this process.

**poetry-relax** provides:
- Automated removal of upper bound constraints specified with `^`
- Safety check if package requirements are still solvable after relaxing constraints
- Upgrade of dependencies after relaxing constraints
- Update of the lock file without upgrading dependencies
- Limit dependency relaxation to specific dependency groups
- Retention of intentional upper bounds indicating true incompatibilities
- CLI messages designed to match Poetry's output

## Installation

The plugin must be installed in Poetry's environment. This requires use of the  `self` subcommand.

```bash
$ poetry self add poetry-relax
```

## Usage

Relax constraints for which Poetry set an upper version:

```bash
$ poetry relax
```

Relax constraints and check that they are resolvable without performing upgrades:

```bash
$ poetry relax --check
```

Relax constraints and upgrade packages:

```bash
$ poetry relax --update
```

Relax constraints and update the lock file without upgrading packages:

```bash
$ poetry relax --lock
```

Preview the changes `poetry relax` would make without modifying the project:

```bash
$ poetry relax --dry-run
```

Relax constraints for specific dependency groups:

```bash
$ poetry relax --only foo --only bar
```

Relax constraints excluding specific dependency groups:

```bash
$ poetry relax --without foo --without bar
```


## Examples

The behavior of Poetry is quite reasonable for local development! `poetry relax` is most useful when used in CI/CD pipelines.

### Relaxing requirements before publishing

Run `poetry relax` before building and publishing a package.

See it at work in [the release workflow for this project](https://github.com/madkinsz/poetry-relax/blob/main/.github/workflows/release.yaml).


### Relaxing requirements for testing

Run `poetry relax --update` before tests to test against the newest possible versions of packages.

See it at work in [the test workflow for this project](https://github.com/madkinsz/poetry-relax/blob/main/.github/workflows/test.yaml).

## Frequently asked questions

> Can this plugin change the behavior of `poetry add` to relax constraints?

Not at this time. The Poetry project states that plugins must not alter the behavior of core Poetry commands. If this behavior would be useful for you, please chime in [on the tracking issue](https://github.com/madkinsz/poetry-relax/issues/5).

> Does this plugin remove upper constraints I've added?

This plugin will only relax constraints specified with a caret (`^`). Upper constraints added with `<` and `<=` will not be changed.

> Is this plugin stable?

This plugin is tested against multiple versions of Poetry and has an integration focused test suite. It is safe to use this in production, though it is recommend to pin versions. Breaking changes will be avoided unless infeasible due to upstream changes in Poetry.

> Will this plugin drop the upper bound on Python itself?

Believe it or not, this is an even more contentious subset of this issue as Poetry will not allow packages with no upper bound on Python to exist alongside those that include one. This basically means that we cannot relax this requirement without breaking the vast majority of use-cases. For this reason, we cannot relax `python^3` at this time. See [the post on the Poetry discussion board](https://github.com/python-poetry/poetry/discussions/3757#discussioncomment-435345) for more details.

## Contributing

This project is managed with Poetry. Here are the basics for getting started.

Clone the repository:
```bash
$ git clone https://github.com/madkinsz/poetry-relax.git
$ cd poetry-relax
```

Install packages:
```bash
$ poetry install
```

Run the test suite:
```bash
$ pytest tests
```

Run linters before opening pull requests:
```bash
$ ./bin/lint check .
$ ./bin/lint fix .
```

## References

There's a lot to read on this topic! It's contentious and causing a lot of problems for maintainers and users.

The following blog posts by Henry Schreiner are quite comprehensive:
- [Should You Use Upper Bound Version Constraints?](https://iscinumpy.dev/post/bound-version-constraints/)
- [Poetry Versions](https://iscinumpy.dev/post/poetry-versions/)

Content from some members of the Python core developer team:
- [Semantic Versioning Will Not Save You](https://hynek.me/articles/semver-will-not-save-you/)
- [Why I don't like SemVer anymore](https://snarky.ca/why-i-dont-like-semver/)
- [Version numbers: how to use them?](https://bernat.tech/posts/version-numbers/)
- [Versioning Software](https://caremad.io/posts/2016/02/versioning-software/)

Discussion and issues in the Poetry project:
- [Please stop pinning to major versions by default, especially for Python itself](https://github.com/python-poetry/poetry/issues/3747)
- [Change default dependency constraint from ^ to >=](https://github.com/python-poetry/poetry/issues/3427)
- [Developers should be able to turn off dependency upper-bound calculations](https://github.com/python-poetry/poetry/issues/2731)
