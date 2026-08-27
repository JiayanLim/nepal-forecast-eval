# Nepal Aurora 1.5 Inference — 002-nepal-eval

**Spec ID**: 002-nepal-eval
**Scope**: Inference-only. Aurora 1.5 (arXiv:2405.13063) forecasts over Nepal.
**Initialisations**: 14 daily 00Z runs, 2026-07-20 through 2026-08-02.
**Forecast horizon**: 168 h (7 days) per initialisation.
**Variables**: 2 m temperature, 10 m wind speed, 10 m wind direction, precipitation.
**ERA5T**: Used for initial conditions (provisional ERA5; ARCO store).
**No metric computation**: This project generates and validates forecast outputs only.

## Source provenance

Inference pipeline derived from the Myanmar Aurora 1.5 evaluation project
(`myanmar-forecast-eval`, unversioned local research pipeline).
Model: `earth2studio.models.px.Aurora1p5`, E2S 0.17.0,
checkpoint `hf://microsoft/aurora@c171214768997594e1a3fc6b8d9bbb489e9d21ab`.

## Spec Kit

`specs/002-nepal-eval/` — constitution, spec, plan, tasks (v1.1, inference-only).

## Repository remotes

- `origin` → `JiayanLim/nepal-forecast-eval` (this repo, Nepal-dedicated)
- `upstream` → source: unversioned local `myanmar-forecast-eval` (no remote push target)

## Do not modify

Myanmar thesis chapters, ERA5 verification archives, or Myanmar metric results are
not present in this repository and must not be added.
