# San Juan (province) spatial reference

`spatial_units.geojson` covers the 19 departamentos of San Juan province (IGN `ign:departamento` layer, INDEC province prefix 70). `unit_id` is `sj_<in1>` (5-digit INDEC department code); `unit_name` is IGN's own `nam` spelling verbatim (accented, source-faithful).

Known naming mismatch: the 2026-07 cohort delivery's `City` column does not match `nam` on exact string equality (observed variants: "Albardon"/"Albardón", "9 de julio"/"9 de Julio", "Ullúm" vs this file's "Ullum"). Normalize at join time, not here.
