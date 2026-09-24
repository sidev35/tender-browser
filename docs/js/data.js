// Loading the tender list. The dashboard never contacts tender websites
// itself: it only reads data/tenders.json, which the scraper writes.

export async function fetchLiveData() {
  const resp = await fetch('data/tenders.json', { cache: 'no-store' });
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  const parsed = await resp.json();
  if (!Array.isArray(parsed)) throw new Error('data/tenders.json is not a JSON array');
  return parsed;
}
