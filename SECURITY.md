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

## Safe-harbour intent

Good-faith research that avoids privacy violations, service disruption,
destructive actions, persistence, and access beyond what is necessary to
demonstrate the issue will be handled constructively. This statement does not
grant permission to test third-party services or datasets outside the
maintainers' authority.
