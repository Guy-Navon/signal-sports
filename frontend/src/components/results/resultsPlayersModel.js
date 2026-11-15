const searchable = (value) => String(value || "").normalize("NFKC").toLowerCase().trim();

export function searchResultPlayers(catalog, query, selected) {
  const needle = searchable(query);
  const ids = new Set(selected);
  return (catalog || []).filter((p) => !ids.has(p.entity_id) &&
    [p.name, p.name_en, ...(p.aliases || [])].some((name) => searchable(name).includes(needle))).slice(0, 8);
}

export function toggleResultPlayer(selected, id) {
  return selected.includes(id) ? selected.filter((p) => p !== id) : [...selected, id];
}

