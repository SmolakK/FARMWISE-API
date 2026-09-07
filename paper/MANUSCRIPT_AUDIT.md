# FARMWISE-API manuscript audit

## Recommendation

Rebuild the manuscript as a software and methods paper centred on the tested
FARMWISE-API contribution. Do not perform a sentence-level polish of the
current draft first. The present draft combines two papers with different
research questions:

1. a bibliometric/text-mining study of agricultural publications; and
2. a software paper about heterogeneous environmental-data integration.

The connection between them is currently asserted rather than demonstrated.
For the stated target, *International Journal of Applied Earth Observation
and Geoinformation*, the API, geospatial harmonisation method, validation, and
empirical results need to become the centre of gravity. The bibliometric study
should either become a short motivation subsection with reproducible methods
in supplementary material, or be developed as a separate paper.

## Highest-priority findings

### 1. There is no Results section

The section `Outputs of FARMWISE API - Exemplary results` contains only
`TBD`. Nevertheless, the abstract and conclusion make strong claims about
performance, integration, quality, and distinctiveness. The repository already
contains material for a defensible evaluation:

- 48 empirical run records: 46 successful and 2 intentional no-data cases;
- coverage-precheck records;
- scaling experiments varying S2 level, bounding-box area, and factor count;
- 13,051 cross-source observations;
- per-source quality reports;
- tests for dispatch, harmonisation, aggregation, adapters, security, and
  packaging.

These should drive a real Results section with stated research questions,
experimental conditions, metrics, uncertainty/repeats, failure reporting, and
figures generated from versioned scripts.

### 2. Source-count and availability claims are ambiguous or outdated

The manuscript repeatedly claims 19 sources and 26 datasets. The current
registry contains 19 source entries, but one registered CDS source is globally
disabled, and two IMGW sources are additionally disabled on public servers.
EGDI and CORRECTIV are retained only as disabled provenance entries and are not
public dispatch sources. The paper must distinguish:

- registered/catalogued sources;
- locally dispatchable sources;
- publicly dispatchable sources;
- protected, deprecated, or non-redistributable sources;
- upstream APIs versus datasets/products.

The appendix is not synchronized with the registry. It includes two EGDI rows
as integrated, omits or inconsistently represents current sources, and gives
several temporal/spatial properties that should be regenerated from the code
and data-licensing register.

### 3. Harmonisation is described incorrectly

The draft says overlapping values are averaged. The implementation now has two
separate, configurable stages:

1. within-source aggregation of multiple records in the same S2 cell/time;
2. cross-source harmonisation using configurable methods and source weights.

Supported methods include weighted mean/median/mode, unweighted variants,
priority, minimum, maximum, and sum. Land cover uses a mode-based policy by
default. This is a central methodological contribution and needs equations,
policy rationale, provenance, edge-case handling, and empirical validation.

### 4. The bibliometric analysis is not yet reproducible enough

The manuscript describes a Scopus search and keyword classification but the
provided Overleaf archive contains neither the exported records nor executable
analysis code. Important issues include:

- a 2026 interval that appears to include an incomplete year;
- unclear exact Scopus query, search date, document-type filters, and deduping;
- classification by broad substring dictionaries without validation against a
  labelled sample;
- unsupported causal interpretation involving DORA, FAIR, and AI awareness;
- a Chow-breakpoint claim in the abstract that is not documented in the body;
- an internal inconsistency stating OA rose to 67.4% in 2005 while describing
  the period and trend differently elsewhere;
- no uncertainty, sensitivity analysis, precision/recall, or inter-rater check.

Unless these materials are supplied and the study is fully validated, the
bibliometric findings should not be a headline contribution.

### 5. The abstract overclaims the evidence

The abstract currently contains nearly the whole argument, including source
counts, bibliometric results, breakpoint tests, implementation details,
competitor comparisons, and policy implications. Several are not demonstrated
in the manuscript. A revised abstract should report:

- the concrete interoperability problem;
- the implemented method;
- the evaluation design;
- two to four quantitative results produced by the repository;
- the bounded contribution and availability statement.

### 6. Architecture coverage is incomplete

The current Methods section omits or underexplains:

- dual Python-library and FastAPI interfaces;
- request and response schema;
- country/bounding-box handling;
- S2 conversion for point, raster, and gridded inputs;
- within-source aggregation;
- temporal-index normalization;
- weighted cross-source harmonisation;
- quality assessment and report persistence;
- dispatch metrics and failure isolation;
- provenance metadata;
- authentication/server workflow;
- dataset acquisition, cache behavior, and licensing safeguards;
- reproducibility environment and software version.

### 7. The figures do not yet explain or validate the system

The same small wrapper diagram is used as both graphical abstract and
architecture figure. It shows only Service -> Wrapper -> API and omits the
registry, coverage pre-check, adapters, S2 normalization, within-source
aggregation, harmonisation, quality assessment, provenance, and output modes.
The bibliometric figures dominate the draft, while there are no API evaluation
figures.

Recommended figures:

1. complete system/data-flow architecture;
2. source coverage matrix or map with availability/licensing status;
3. coverage pre-check effectiveness and dispatch outcomes;
4. scaling of latency/memory/output size;
5. cross-source comparison for valid overlap scenarios;
6. one end-to-end use case with input region, S2 output, and provenance.

### 8. LaTeX and bibliography need cleanup

- Missing bibliography keys: `EU2022`, `EUComistion25`, and `Gebbers2010`.
- Duplicate bibliography key: `Stephen2024`.
- Duplicate label: `Meth:sub1` is used for two subsections.
- The graphical abstract is a placeholder-quality duplicate.
- A second `\appendix` command is unnecessary.
- The template retains substantial instructional boilerplate.
- Corresponding-author/email metadata are missing.
- Affiliation 5 has an apparent French address despite naming a Wroclaw
  University department.
- Naming varies among `FARMWISE API`, `Farmwise API`, and `FARMWISE-API`.
- `FARMWISTE_API_dt.bib` contains a likely typo in its filename.
- Multiple sentences need substantive rewriting, not copy-editing.

## Proposed paper structure

1. **Introduction**
   - heterogeneous European agricultural/environmental sources;
   - concrete interoperability gap;
   - related integration systems;
   - explicit contributions and paper scope.
2. **System requirements and supported data landscape**
   - user stories and query model;
   - source/product inventory and licensing categories;
   - output/provenance contract.
3. **Architecture and methods**
   - adapter registry and coverage pre-check;
   - asynchronous failure-isolated dispatch;
   - S2 spatial normalization;
   - temporal normalization and within-source aggregation;
   - cross-source harmonisation;
   - quality assessment, provenance, and interfaces.
4. **Evaluation design**
   - research questions;
   - scenarios, environment, versions, repetitions, and metrics;
   - negative controls and upstream-service limitations.
5. **Results**
   - functional coverage and dispatch avoidance;
   - latency/memory scaling;
   - cross-source agreement/disagreement;
   - quality metrics and failure behavior;
   - end-to-end case study.
6. **Discussion**
   - what the system enables;
   - comparison with related platforms using explicit criteria;
   - limits from source availability, licensing, calibration, and live APIs;
   - threats to validity.
7. **Software and data availability**
   - release/version, repository, license, archive DOI, environment;
   - data-source terms and non-redistributable inputs.
8. **Conclusion**

## Proposed evaluation questions

- **RQ1:** Does the spatial-temporal-thematic pre-check prevent irrelevant
  upstream requests while retaining eligible sources?
- **RQ2:** How do latency, traced memory, returned cell count, and output size
  scale with S2 level, bounding-box area, and number of factors?
- **RQ3:** How consistently do overlapping sources represent the same variable
  after S2 and temporal normalization?
- **RQ4:** How do within-source aggregation and cross-source harmonisation
  policies affect the resulting values?
- **RQ5:** How does the system behave when sources are unavailable, empty,
  restricted, or outside requested coverage?

## Immediate next actions

1. Confirm that the bibliometric work will be shortened/supplementary or split
   into a separate paper.
2. Confirm the target journal and article type.
3. Preserve the imported file as the baseline and create a modular manuscript
   (`main.tex` plus section files) for the rewrite.
4. Regenerate the source inventory directly from the registry and
   `DATA_LICENSES.md`.
5. turn the existing evaluation inputs into reproducible tables and figures;
6. write Methods and Results from code/evidence before rewriting the abstract,
   introduction, discussion, and conclusion.

## Verification constraints in this environment

No LaTeX compiler is currently available on the command path, so the imported
source could not be compiled locally during this audit. The citation/label and
content checks above were performed structurally. The Python test runner is
also not installed in the active interpreter, so a fresh test-suite result has
not yet been produced here.
