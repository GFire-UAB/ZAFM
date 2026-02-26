# Preprocessing helpers

These scripts help you prepare inputs for ZAFM v2.

Typical steps:
1. Clip ESA WorldCover (WCM) to your region of interest (ROI) → `<REG>__WCM_4326_clip.tif`
2. Align/resample FirEUrisk to the exact WCM grid → `align_fire_to_wcm.py`
3. Fix invalid placeholder values (optional) → `fix_fire_values.py`

See the repository `README.md` for the full workflow and command examples.
