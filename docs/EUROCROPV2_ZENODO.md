# EuroCropV2 `points.csv`: opis rekordu Zenodo

Ten dokument służy wyłącznie do ręcznego opublikowania istniejącego pliku
`points.csv`. Nie tworzy ani nie przetwarza danych.

Przed publikacją potwierdź, że posiadany plik faktycznie pochodzi z
EuroCropsV2 oraz że opis zmian poniżej odpowiada sposobowi, w jaki został
utworzony. Jeżeli nie da się potwierdzić pochodzenia lub transformacji pliku,
nie publikuj go jako zweryfikowanej pochodnej.

## Pola rekordu Zenodo

- **Resource type:** Dataset
- **Title:** `FARMWISE point representation of EuroCropsV2`
- **Creators:** wpisz rzeczywistych twórców kompilacji `points.csv`; nie wpisuj
  autorów EuroCropsV2 jako twórców pochodnej, jeżeli jej nie przygotowali
- **Publication date:** data publikacji rekordu
- **Version:** `1.0.0` dla pierwszego opublikowanego pliku
- **Access:** Public
- **License:** Creative Commons Attribution 4.0 International (`CC BY 4.0`)
- **Keywords:** `EuroCropsV2`, `agricultural parcels`, `crop declarations`,
  `FARMWISE`, `European Union`, `point data`
- **Related identifier:**
  `10.2905/b9fb9e67-78a9-4327-9d59-39a928d812d3`, relacja
  `isDerivedFrom`

## Opis do wklejenia

> This record contains the `points.csv` dataset used by the FARMWISE
> EuroCropV2 adapter. It is a point-based, reformatted derivative of the
> European Commission Joint Research Centre EuroCropsV2 parcel dataset. The
> file contains longitude and latitude coordinates together with annual crop
> codes (`cYYYY`) and annual parcel identifiers (`cfYYYY`). The source parcel
> data were converted to point records and serialized as CSV for spatial
> filtering and S2-cell aggregation in FARMWISE. [Before publication, replace
> this sentence with the confirmed method used to choose each point, for
> example centroid or interior representative point.] Coverage, years and any
> omitted records: [DESCRIBE OR INSERT "not independently verified"].

## Wymagana atrybucja

W opisie lub osobnym pliku `LICENSE.txt` umieść:

> Source data: European Commission, Joint Research Centre (2026):
> EuroCropsV2 [Dataset].
> https://doi.org/10.2905/b9fb9e67-78a9-4327-9d59-39a928d812d3
>
> Source data copyright: European Union, 1995-2026. Licensed under Creative
> Commons Attribution 4.0 International:
> https://creativecommons.org/licenses/by/4.0/
>
> Changes: parcel data were reformatted into a point-based CSV representation
> for FARMWISE. [ADD THE CONFIRMED POINT-SELECTION AND CRS TRANSFORMATION
> METHOD.] No endorsement by the European Commission or Joint Research Centre
> is implied.

## Pliki do umieszczenia w rekordzie

1. `points.csv`
2. `LICENSE.txt` z powyższą atrybucją i potwierdzonym opisem zmian
3. opcjonalnie `README.md` opisujący kolumny, pokrycie przestrzenne i lata
4. opcjonalnie `SHA256SUMS` z sumą kontrolną pliku

Sumę SHA-256 można policzyć w PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 "D:\ścieżka\points.csv"
```

## Po opublikowaniu

W `core/utils/data_manifest.py`, w rekordzie
`EuroCropV2/data/points.csv`, zastąp:

- `REPLACE_ME` w URL numerycznym identyfikatorem rekordu Zenodo,
- `REPLACE_ME` w `sha256` obliczoną sumą SHA-256,
- `size_mb` rzeczywistym rozmiarem pliku.

Adapter pozostaje bez zmian i nadal pobiera dokładnie
`EuroCropV2/data/points.csv`.
