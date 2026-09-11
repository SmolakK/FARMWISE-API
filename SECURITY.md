# Security Policy

## Supported versions

FARMWISE-API is currently in an alpha release cycle. Security fixes are
provided for the latest released minor version only.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier versions | No |

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue,
discussion, pull request, evaluation output, or dataset.

Use the repository's private
[GitHub Security Advisory form](https://github.com/SmolakK/FARMWISE-API/security/advisories/new).

Include, where possible:

- the affected version, component, and deployment mode;
- a minimal reproduction or proof of concept;
- the expected and observed behaviour;
- the potential impact and any known mitigations;
- whether credentials, personal information, or restricted data may have
  been exposed.

Do not include live credentials, access tokens, private datasets, or personal
data. Replace them with synthetic examples and state what kind of information
was removed.

The maintainers aim to acknowledge a complete report within five business
days. We will coordinate validation, remediation, release timing, and public
disclosure with the reporter. Timelines may vary with severity and with fixes
required in upstream data services or dependencies.

## Scope

Reports about FARMWISE-API source code, packaged artifacts, authentication,
download endpoints, dependency handling, and default deployment configuration
are in scope. Availability or security problems belonging exclusively to an
upstream data provider should normally be reported to that provider, but we
welcome reports showing that FARMWISE-API handles such failures unsafely.

Data licensing questions and requests for access to restricted datasets are
not security vulnerabilities. Follow [DATA_LICENSES.md](DATA_LICENSES.md) and
do not attach restricted source or derived data to a security report unless
the maintainers explicitly provide an approved secure transfer method.

## Known dependency risks

### Pickle deserialisation in diskcache

`diskcache` (a transitive dependency of `wetterdienst`) serialises cached
values with `pickle` in every release up to and including 5.6.3, which is the
newest. Anything able to write into a diskcache directory can therefore run
arbitrary code inside the process that next reads that cache. There is no
fixed version to upgrade to.

FARMWISE does not rely on that cache and does not create one. The DWD adapter
passes `cache_disable=True` to every `wetterdienst` request, which leaves
wetterdienst's listings cache unconstructed rather than merely unused: no
`diskcache.Cache` object and no cache directory. Two tests in
`tests/test_wetterdienst_dwd.py` hold this in place - one asserts the setting
is still sent, the other asserts that a disabled cache constructs no
`diskcache.Cache`. The full test suite has been run with `diskcache.Cache`
instrumented, confirming zero instantiations across all code paths.

Operators who re-enable wetterdienst caching take on this risk, and should
then ensure the cache directory is writable only by the account running the
service and is not on a shared or world-writable volume.

## Safe-harbour intent

Good-faith research that avoids privacy violations, service disruption,
destructive actions, persistence, and access beyond what is necessary to
demonstrate the issue will be handled constructively. This statement does not
grant permission to test third-party services or datasets outside the
maintainers' authority.
