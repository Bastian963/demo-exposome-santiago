# Buenos Aires AMBA spatial reference

`spatial_units.geojson` merges the 15 CABA comunas (GCBA) with the 40 AMBA partidos of Buenos Aires province (IGN), including Gran La Plata (La Plata, Berisso, Ensenada). `unit_id` disambiguates the two admin levels (`caba_comuna_NN` / `pba_<in1>`); `unit_name` is the display name (comunas use the "Comuna N · barrios" composite, partidos use IGN's own spelling). Names are source-faithful (not re-accented or stripped). Known limitation: GCBA/IGN geometries have small overlap/gap slivers along the CABA/AMBA boundary; not clipped in v1.
