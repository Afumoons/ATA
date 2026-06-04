"""Adaptive ML shadow-prediction subsystem for ATA.

Stage 1 is read-only: it can build datasets, track model metadata, journal
predictions, and label outcomes, but it must not place or modify trades.
"""
