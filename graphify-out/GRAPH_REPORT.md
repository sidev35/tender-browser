# Graph Report - tender-radar-repo  (2026-09-23)

## Corpus Check
- Corpus is ~13,538 words - fits in a single context window. You may not need a graph.

## Summary
- 102 nodes · 142 edges · 8 communities (7 shown, 1 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.83)
- Token cost: 62,781 input · 0 output

## Community Hubs (Navigation)
- Dashboard Alerts & Rendering
- Scraper Core Pipeline
- Workflow & Project Overview
- Email Digest Notifier
- JS Portal Debug Helper
- Portal Fetchers & Parsers
- Official Site Lookup Modal
- Category Filter Flags

## God Nodes (most connected - your core abstractions)
1. `checkForAlerts()` - 9 edges
2. `run()` - 8 edges
3. `render()` - 8 edges
4. `send_digest()` - 6 edges
5. `parse_generic_table()` - 6 edges
6. `parse_gepnic_table()` - 5 edges
7. `scrape job (cron every 15 min)` - 5 edges
8. `Find on official site modal` - 5 edges
9. `refreshData()` - 5 edges
10. `inspect_form_in()` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Auto-refresh every 10 min + visibilitychange` --semantically_similar_to--> `15-minute cron schedule`  [INFERRED] [semantically similar]
  docs/index.html → .github/workflows/update-tenders.yml
- `Manual paste JSON merge (applyUpdate handler)` --semantically_similar_to--> `Merge-and-retain until due date behavior`  [INFERRED] [semantically similar]
  docs/index.html → README.md
- `checkForAlerts()` --semantically_similar_to--> `Digest throttling (MIN_HOURS_BETWEEN_DIGESTS / digest_state.json)`  [INFERRED] [semantically similar]
  docs/index.html → README.md
- `checkForAlerts()` --implements--> `DUE_SOON_DAYS closing-soon window (7 days)`  [INFERRED]
  docs/index.html → README.md
- `run()` --calls--> `send_digest()`  [EXTRACTED]
  scraper.py → notify.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Scrape-commit-display tender data pipeline** — _github_workflows_update_tenders_scrape_job, _github_workflows_update_tenders_commit_step, readme_tenders_json, docs_index_fetchlivedata, docs_index_dashboard [INFERRED 0.95]
- **Dashboard new/closing-soon alert flow** — docs_index_refreshdata, docs_index_checkforalerts, docs_index_getknownids, docs_index_getduesoonnotified, docs_index_showtoast, docs_index_maybenativenotify [EXTRACTED 1.00]
- **Email digest system** — readme_email_digest, readme_digest_throttling, email_template_digest_template, email_template_placeholders, readme_due_soon_window [INFERRED 0.85]

## Communities (8 total, 1 thin omitted)

### Community 0 - "Dashboard Alerts & Rendering"
Cohesion: 0.11
Nodes (17): Commit updated tender data step, checkForAlerts(), daysUntil(), fetchLiveData(), fmtDue(), Manual paste JSON merge (applyUpdate handler), maybeNativeNotify(), refreshData() (+9 more)

### Community 1 - "Scraper Core Pipeline"
Cohesion: 0.12
Nodes (22): bs4, hashlib, re, days_until(), extract_due_date(), fetch(), fetch_eesl_tenders(), fetch_generic_homepage() (+14 more)

### Community 2 - "Workflow & Project Overview"
Cohesion: 0.17
Nodes (12): Update EV charging tenders workflow, update-tenders concurrency group, 15-minute cron schedule, Install Playwright browser step, scrape job (cron every 15 min), Auto-refresh every 10 min + visibilitychange, Tender Radar dashboard (docs/index.html), Known ceiling: 10-latest homepage widget (+4 more)

### Community 3 - "Email Digest Notifier"
Cohesion: 0.25
Nodes (10): datetime, json, _format_list(), _last_sent(), Email digest for Tender Radar — sent from the same GitHub Actions run as the…, _record_sent(), _render(), send_digest() (+2 more)

### Community 4 - "JS Portal Debug Helper"
Cohesion: 0.25
Nodes (10): describe_element(), inspect(), inspect_form(), inspect_form_in(), Debug helper: point this at a candidate JS-rendered tender portal to see what…, Actually performs the search (fill + click, same as fetch_js_interactive_search…, run_search_and_dump(), _safe_visible() (+2 more)

### Community 5 - "Portal Fetchers & Parsers"
Cohesion: 0.18
Nodes (10): fetch_gepnic_homepage(), fetch_js_interactive_search(), fetch_js_rendered_table(), parse_generic_table(), parse_gepnic_table(), Parses the 'Latest Tenders' table found on NIC GePNIC-based portals. Structure:…, Fallback parser: same idea as GePNIC but looser, for other portal layouts., The free homepage "activeTenders" widget — the 10 most-recently-posted tenders… (+2 more)

### Community 6 - "Official Site Lookup Modal"
Cohesion: 0.28
Nodes (8): fieldRow(), openTenderInfoModal(), Autofill bookmarklet, Find on official site modal, NIC GePNIC e-procurement engine, searchUrl stable search page, sources.json source registry, TYPE_FETCHERS safety net

## Knowledge Gaps
- **6 isolated node(s):** `update-tenders concurrency group`, `CATEGORY_KEYWORDS match filter`, `TENDER_SHOW_ALL flag`, `Tender Radar dashboard (docs/index.html)`, `Template placeholders (NEW_COUNT, DUE_SOON_COUNT, RUN_TIME, NEW_SECTION, DUE_SOON_SECTION, DASHBOARD_URL)` (+1 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 34 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `render()` connect `Dashboard Alerts & Rendering` to `Official Site Lookup Modal`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `openTenderInfoModal()` connect `Official Site Lookup Modal` to `Dashboard Alerts & Rendering`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `checkForAlerts()` (e.g. with `Digest throttling (MIN_HOURS_BETWEEN_DIGESTS / digest_state.json)` and `DUE_SOON_DAYS closing-soon window (7 days)`) actually correct?**
  _`checkForAlerts()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `update-tenders concurrency group`, `CATEGORY_KEYWORDS match filter`, `TENDER_SHOW_ALL flag` to the rest of the system?**
  _6 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Dashboard Alerts & Rendering` be split into smaller, more focused modules?**
  _Cohesion score 0.11067193675889328 - nodes in this community are weakly interconnected._
- **Should `Scraper Core Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.1225296442687747 - nodes in this community are weakly interconnected._