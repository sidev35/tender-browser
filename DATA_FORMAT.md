# What a saved tender looks like

Every tender the scraper finds is saved in `docs/data/tenders.json`, one
entry per tender. The dashboard reads that file and nothing else. This page
describes each field; the code's own definition is the `Tender` class in
`tender_radar/models.py`, and a test checks that every saved record matches.

## Example

```json
{
  "id": "AUTO-fd4ab1dcb6",
  "desc": "Supply, Installation, Testing and Commissioning of Electrical Infrastructure ... at the Charging Station at Gotri ...",
  "refNo": "PRO No. 394/2026-27",
  "location": null,
  "value": "₹2.55 Cr",
  "dueDate": "2026-10-03",
  "category": "Charger Supply & Installation",
  "source": "Gujarat nProcure (keyword search)",
  "url": "https://tender.nprocure.com/",
  "linkType": "search",
  "firstSeen": "2026-09-23"
}
```

## Fields

| Field | Always there? | What it is | Shown on the card? |
|---|---|---|---|
| `id` | Yes | A fingerprint made from the website and the tender's title (or the site's own tender number). The same tender always gets the same id, which is how duplicates are avoided. Looks like `AUTO-` plus 10 letters/digits. | No |
| `desc` | Yes | The tender's title, cleaned up. | Yes, as the title |
| `category` | Yes | Which kind of EV tender it is, from `config/categories.json`. | Yes, as the badge and the group heading |
| `source` | Yes | Which website it came from (the `name` in `sources.json`). | Yes (without the part in brackets) |
| `url` | Yes | Where the card's button goes. | Via the button |
| `linkType` | Yes | `direct`: `url` opens this exact tender (button **View tender ↗**). `search`: `url` is the website's search page (button **Copy title & open portal ↗**). | Decides the button |
| `firstSeen` | Yes | The date the scraper first found it, `yyyy-mm-dd`. | Yes, "Tracked since" |
| `dueDate` | When known | The closing date, `yyyy-mm-dd`. Empty if the website didn't show one. | Yes, the date badge and "days left" |
| `value` | When disclosed | The amount, already formatted, e.g. `₹2.55 Cr` or `₹26.09 Lakh`. | Yes, or "Value not disclosed" |
| `refNo` | When found | The issuing authority's reference number. | No |
| `location` | When found | State or city, when the website shows one. | No |

Missing values are stored as `null`.

## Rules the scraper follows

- **A tender is never added twice:** if its `id` is already in the file, the
  saved entry is kept (its title and value are refreshed, in case they're
  now extracted better).
- **Tenders are removed once their `dueDate` has passed.** Tenders with no
  known due date are kept, because hiding them silently would be worse.
- **Nothing else edits this file.** It's written only by the scraper (locally
  or by the scheduled GitHub workflow).
