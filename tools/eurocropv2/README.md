# Publishing the FARMWISE EuroCropsV2 derivative

This directory contains the complete reproducible workflow for creating and
publishing the point dataset used by the EuroCropV2 adapter. The source is the
official JRC EuroCropsV2.01 dataset; the output is a derived dataset licensed
under CC BY 4.0.

The official stack files are large. Plan for tens of gigabytes of downloads,
additional working space, and a multi-hour build. The generated CSV is gzip
compressed because Zenodo accepts at most 50 GB per standard deposit and the
compressed file can be consumed directly by DuckDB.

## 1. Install publication dependencies

From the repository root, in the FARMWISE environment:

```powershell
python -m pip install -e ".[eurocrop-publish]"
```

## 2. Build the data and provenance

Choose a large data directory outside Git. This command downloads missing
official regional stack files and then builds the full derivative:

```powershell
python -m tools.eurocropv2.build_points `
  --source-dir "D:\data\EuroCropsV2\source" `
  --output "D:\data\EuroCropsV2\points.csv.gz" `
  --provenance "D:\data\EuroCropsV2\PROVENANCE.json" `
  --download
```

The default region list is the complete set of stack files published in the
official `gpqtv201` snapshot. `--regions` may be used for
a test or regional derivative, but such an output must not be described on
Zenodo as the complete dataset. Existing source files are reused. Existing
outputs are protected unless `--overwrite` is explicitly supplied.

Before continuing, inspect the counts and region list in `PROVENANCE.json`.
For a full release, all default regions must be present and the output checksum
must match the file.

## 3. Prepare the Zenodo sidecars

Use your real citation name. Affiliation and ORCID are recommended but
optional:

```powershell
python -m tools.eurocropv2.prepare_zenodo `
  --data-file "D:\data\EuroCropsV2\points.csv.gz" `
  --provenance "D:\data\EuroCropsV2\PROVENANCE.json" `
  --output-dir "D:\data\EuroCropsV2\zenodo-deposit-v1.0.0" `
  --creator-name "Surname, Given names" `
  --creator-affiliation "Your institution" `
  --creator-orcid "0000-0000-0000-0000" `
  --version "1.0.0"
```

This validates the data checksum and creates:

- `README.md`
- `DATA_DICTIONARY.md`
- `LICENSE.txt`
- `PROVENANCE.json`
- `SHA256SUMS`
- `zenodo_metadata.json`
- `UPLOAD_FILES.txt`

The data file is not copied, so the preparation step does not require another
multi-gigabyte allocation. `UPLOAD_FILES.txt` contains the files to upload.

## 4. Test in Zenodo Sandbox

Create a personal token at `https://sandbox.zenodo.org/account/settings/applications/tokens/new/`
with deposit permissions. Store it only in the current process environment:

```powershell
$env:ZENODO_TOKEN = Read-Host -MaskInput "Sandbox Zenodo token"
python -m tools.eurocropv2.upload_zenodo `
  --metadata "D:\data\EuroCropsV2\zenodo-deposit-v1.0.0\zenodo_metadata.json" `
  --upload-list "D:\data\EuroCropsV2\zenodo-deposit-v1.0.0\UPLOAD_FILES.txt" `
  --sandbox
Remove-Item Env:ZENODO_TOKEN
```

Without `--publish`, the script only creates or updates a draft. Review the
draft in the browser. Do not publish the sandbox test unless you specifically
want a public sandbox record.

## 5. Upload the production draft

Create a production token at Zenodo, set `ZENODO_TOKEN` as above, and repeat
without `--sandbox`. The default remains a draft:

```powershell
python -m tools.eurocropv2.upload_zenodo `
  --metadata "D:\data\EuroCropsV2\zenodo-deposit-v1.0.0\zenodo_metadata.json" `
  --upload-list "D:\data\EuroCropsV2\zenodo-deposit-v1.0.0\UPLOAD_FILES.txt"
```

You may instead create a Zenodo upload manually and copy the fields from
`zenodo_metadata.json`. Select resource type **Dataset**, visibility **Public**,
and licence **Creative Commons Attribution 4.0 International**. Upload exactly
the paths listed in `UPLOAD_FILES.txt`.

Review title, creator name, affiliation, ORCID, description, source DOI,
licence, version, file list, total size and checksums. Zenodo's standard limit
is 100 files and 50 GB total; request an increased quota before publication if
the prepared deposit exceeds that limit.

Publish only after this review. To publish through the script, rerun it with
the returned `--deposition-id` and the explicit `--publish` flag. Publishing
registers the DOI and makes the files immutable except for Zenodo's limited
correction window.

## 6. Connect the published record to FARMWISE

After publication, use the numeric Zenodo record ID and the exact generated
file:

```powershell
python -m tools.eurocropv2.finalize_manifest `
  --record-id "12345678" `
  --data-file "D:\data\EuroCropsV2\points.csv.gz"
```

This replaces the marked EuroCropsV2 block in
`core/utils/data_manifest.py` with the permanent download URL, SHA-256 and
size. Verify the URL in a clean cache and run the adapter tests before
committing the manifest update.

## Licence checklist

- Retain `LICENSE.txt` in the deposit.
- Use CC BY 4.0 for the dataset record.
- Cite the JRC source dataset and DOI.
- State that polygons were converted to representative points and coordinates
  transformed.
- Retain provenance and checksums.
- Do not imply endorsement by the European Commission or JRC.
- Create a new Zenodo version when the data file changes.

The source licence permits redistribution of this derivative subject to
attribution and change indication. This workflow documents those conditions;
it is not a substitute for legal advice for additional third-party material.
