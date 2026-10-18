"""Refinement stages, in execution order. Append a new stage at the end."""

from app.canonical.stages.abrev import abrev
from app.canonical.stages.ancora import ancora
from app.canonical.stages.plural import plural
from app.canonical.stages.ruido import ruido

STAGES = [ancora, plural, abrev, ruido]
