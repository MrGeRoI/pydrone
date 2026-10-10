"""Native game definitions and runtime settings, loaded once from JSON."""
import json
from pathlib import Path


DATA=Path(__file__).resolve().parents[1]/'data/rules'
with (DATA/'entities.json').open(encoding='utf-8') as source:
    entities=json.load(source)
STRUCTURES=entities['structures']
UNIT_TYPES=entities['units']
ENEMY_TYPES=entities['enemies']
with (DATA/'arenas.json').open(encoding='utf-8') as source:
    ARENAS=json.load(source)

with (DATA/'runtime.json').open(encoding='utf-8') as source:
    PARALLEL=json.load(source)['parallel']
for key in ('max_workers','minimum_pairs','minimum_enemies','minimum_units','spatial_minimum_targets','spatial_minimum_pairs'):
    if type(PARALLEL[key]) is not int or PARALLEL[key]<1:
        raise ValueError(f'runtime.json: parallel.{key} must be a positive integer')
