export function joinAnnualRecords(master, annual) {
  const records = annual?.records;
  if (!master || !Array.isArray(master.features) || !Array.isArray(records)) {
    throw new Error("Annual asset requires master features and tabular records");
  }
  const byId = new Map();
  for (const record of records) {
    const id = record?.spatial_id;
    if (id === undefined || id === null) throw new Error("Annual record has no spatial_id");
    const key = String(id);
    if (byId.has(key)) throw new Error(`Duplicate annual spatial_id: ${key}`);
    byId.set(key, record);
  }
  const features = master.features.map((feature) => {
    const properties = feature.properties || {};
    const key = String(properties.spatial_id ?? properties.slug ?? "");
    const record = byId.get(key);
    if (!record) throw new Error(`Annual asset is missing spatial_id: ${key}`);
    return { ...feature, properties: { ...properties, ...record } };
  });
  if (features.length !== byId.size) {
    throw new Error(
      `Annual asset coverage mismatch: master=${features.length}, records=${byId.size}`,
    );
  }
  return { type: "FeatureCollection", features };
}
