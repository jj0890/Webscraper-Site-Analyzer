"""
Scan Library — persistent storage for design evidence across sessions.

Makes the tool a research companion instead of a forensics report:
  - Every scan is saved automatically (or on-demand)
  - Design properties are indexed for fast cross-scan querying
  - Individual findings (sections, components) can be saved and tagged
  - Cross-scan patterns emerge from accumulated evidence

Storage: SQLite (single file, no server, works offline)
Location: scan_library.db in the project root (gitignored)

Schema:
    scans     — one row per full page scan, indexed design properties + full evidence JSON
    findings  — tagged sections/components saved from the dwell panel or blueprints
"""

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(__file__), 'scan_library.db')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id                 TEXT PRIMARY KEY,
    url                TEXT NOT NULL,
    domain             TEXT NOT NULL,
    scanned_at         REAL NOT NULL,           -- Unix timestamp
    analysis_mode      TEXT,
    access_strategy    TEXT,
    overall_confidence INTEGER,

    -- Indexed design properties (extracted at save time for fast querying)
    primary_font       TEXT,
    all_fonts          TEXT,                    -- JSON array
    primary_color      TEXT,
    color_palette      TEXT,                    -- JSON array of hex strings
    spacing_base_unit  TEXT,
    motion_strategy    TEXT,
    motion_durations   TEXT,                    -- JSON array of ms values
    content_density_pct REAL,
    brand_personality  TEXT,
    consistency_score  REAL,
    page_type          TEXT,
    layout_pattern     TEXT,
    css_sophistication INTEGER,

    -- Full evidence (compressed with zlib, base64-encoded)
    evidence_json      TEXT NOT NULL,

    notes              TEXT                     -- user free-text annotation
);

CREATE INDEX IF NOT EXISTS idx_scans_domain         ON scans(domain);
CREATE INDEX IF NOT EXISTS idx_scans_primary_font   ON scans(primary_font);
CREATE INDEX IF NOT EXISTS idx_scans_primary_color  ON scans(primary_color);
CREATE INDEX IF NOT EXISTS idx_scans_motion_strategy ON scans(motion_strategy);
CREATE INDEX IF NOT EXISTS idx_scans_scanned_at     ON scans(scanned_at DESC);

CREATE TABLE IF NOT EXISTS findings (
    id          TEXT PRIMARY KEY,
    scan_id     TEXT NOT NULL,
    scan_url    TEXT NOT NULL,
    saved_at    REAL NOT NULL,

    -- What was saved
    label       TEXT,                           -- user-provided label
    tags        TEXT,                           -- JSON array of tag strings
    notes       TEXT,

    -- Section context (from the dwell panel)
    section_index   INTEGER,
    section_data    TEXT NOT NULL,              -- JSON with rect, styles, blueprint

    FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_findings_scan_id  ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_findings_saved_at ON findings(saved_at DESC);
"""


# ── DB connection ────────────────────────────────────────────────────────────

@contextmanager
def _db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flatten_evidence(evidence: Dict) -> Dict:
    """
    Smart-nav evidence nests per-page metrics under ``page_results.home``.
    This merges them flat so property extractors work regardless of mode.

    Strategy: start with home page keys (typography, colors, motion_tokens …),
    then overlay top-level smart-nav keys (design_system_consistency, _meta,
    analysis_mode …) so the aggregated values always win.
    ``page_results`` itself is excluded to avoid confusion.
    """
    if 'page_results' not in evidence:
        return evidence

    home_ev = evidence.get('page_results', {}).get('home', {})
    if not home_ev:
        return evidence

    merged = dict(home_ev)
    for k, v in evidence.items():
        if k != 'page_results':
            merged[k] = v          # smart-nav top-level overrides home duplicates
    return merged


def _infer_motion_strategy(motion_tokens: Dict) -> 'str | None':
    """
    Lightweight fallback classifier for scans saved before motion_narrative
    was wired into the pipeline.  Uses only the duration_scale values.

    Mirrors the thresholds in DeepEvidenceEngine._synthesize_motion_narrative()
    so backfilled values are consistent with live scans.
    """
    if not isinstance(motion_tokens, dict):
        return None
    details = motion_tokens.get('details', {})
    if not isinstance(details, dict):
        return None
    ds = details.get('duration_scale', {})
    values = ds.get('values_ms', []) if isinstance(ds, dict) else []
    if not values:
        return 'minimal'
    count = len(values)
    max_ms = max(values)
    if count <= 2 and max_ms <= 300:
        return 'performance-conscious'
    if count >= 5 or max_ms > 800:
        return 'expressive'
    return 'layered'


# ── Extract indexed properties from evidence ──────────────────────────────────

def _index_evidence(evidence: Dict) -> Dict:
    """
    Pull the design properties used for cross-scan search out of the full
    evidence dict and return a flat dict ready to insert into the scans table.

    Handles both single-page evidence (flat keys) and smart-nav evidence
    (per-page keys nested under ``page_results.home``).
    """
    evidence = _flatten_evidence(evidence)

    def _safe(fn):
        try:
            return fn()
        except Exception:
            return None

    typo   = evidence.get('typography', {})
    colors = evidence.get('colors', {})
    palette = colors.get('palette', {})
    spacing = evidence.get('spacing_scale', {})
    motion  = evidence.get('motion_tokens', {})
    motion_narrative = motion.get('narrative', {}) if isinstance(motion, dict) else {}
    spatial = evidence.get('spatial_composition', {})
    brand   = evidence.get('brand_personality', {})
    layout  = evidence.get('layout', {})
    meta    = evidence.get('meta_info', {})
    css     = evidence.get('css_analytics', {})
    dsc     = evidence.get('design_system_consistency', {})
    meta2   = evidence.get('_meta', {})

    # Fonts
    fonts = typo.get('fonts', typo.get('ui_fonts', []))
    if isinstance(fonts, dict):
        fonts = list(fonts.values())
    primary_font = None
    if fonts and isinstance(fonts[0], str):
        # Take first named font before comma
        import re
        parts = [p.strip().strip('"\'') for p in fonts[0].split(',')]
        candidates = [p for p in parts if p and not p.startswith(('ui-', 'system', '-apple', 'Segoe'))]
        primary_font = candidates[0] if candidates else fonts[0]

    # Colors — build a flat hex list
    def _to_hex(c):
        if not isinstance(c, str):
            return None
        if c.startswith('#'):
            return c.upper()
        import re
        m = re.match(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', c)
        if m:
            return '#{:02X}{:02X}{:02X}'.format(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None

    all_palette_colors = []
    if isinstance(palette, dict):
        for bucket in ['intentional', 'primary', 'secondary']:
            for c in palette.get(bucket, [])[:3]:
                h = _to_hex(c)
                if h:
                    all_palette_colors.append(h)
    primary_color = all_palette_colors[0] if all_palette_colors else None

    # Spacing
    base_unit = spacing.get('base_unit')
    if isinstance(base_unit, (int, float)):
        base_unit = f"{base_unit}px"

    # Motion — prefer narrative.strategy; fall back to lightweight inference
    motion_strategy = motion_narrative.get('strategy') if isinstance(motion_narrative, dict) else None
    if motion_strategy is None:
        motion_strategy = _infer_motion_strategy(motion)
    motion_durations = _safe(lambda: motion.get('details', {}).get('duration_scale', {}).get('values_ms', []))

    # Density
    ws = spatial.get('whitespace_analysis', {}) if isinstance(spatial, dict) else {}
    density = ws.get('content_density_pct')

    # Brand
    brand_pat = brand.get('pattern', '') if isinstance(brand, dict) else ''

    return {
        'primary_font':       primary_font,
        'all_fonts':          json.dumps(fonts[:5]) if fonts else '[]',
        'primary_color':      primary_color,
        'color_palette':      json.dumps(all_palette_colors[:8]),
        'spacing_base_unit':  str(base_unit) if base_unit else None,
        'motion_strategy':    motion_strategy,
        'motion_durations':   json.dumps(motion_durations) if motion_durations else '[]',
        'content_density_pct': density,
        'brand_personality':  brand_pat[:120] if brand_pat else None,
        'consistency_score':  dsc.get('overall_consistency_score') if isinstance(dsc, dict) else None,
        'page_type':          meta.get('page_type') or meta2.get('page_type'),
        'layout_pattern':     layout.get('pattern') if isinstance(layout, dict) else None,
        'css_sophistication': css.get('sophistication_score') if isinstance(css, dict) else None,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def save_scan(
    url: str,
    evidence: Dict,
    analysis_mode: str = 'single',
    notes: str = '',
    scan_id: str = None,
) -> str:
    """
    Persist a completed scan to the library.

    Returns the scan_id (UUID string). Upserts on (url, analysis_mode) so
    re-scanning the same URL updates the existing record rather than
    duplicating it.

    Args:
        url:           The scanned URL.
        evidence:      Full evidence dict from DeepEvidenceEngine.extract_all().
        analysis_mode: 'single', 'smart-nav', 'multi-template', etc.
        notes:         Optional free-text annotation.
        scan_id:       Optional explicit ID (generated if not provided).

    Returns:
        scan_id string.
    """
    from urllib.parse import urlparse
    scan_id = scan_id or str(uuid.uuid4())
    domain  = urlparse(url).netloc or url

    # Flatten smart-nav nesting so _meta / access_strategy are reachable
    flat = _flatten_evidence(evidence)
    meta2 = flat.get('_meta', {})
    overall_conf    = meta2.get('overall_confidence')
    access_strategy = flat.get('access_strategy', 'unknown')

    indexed = _index_evidence(evidence)   # _index_evidence flattens internally

    try:
        evidence_json = json.dumps(evidence, default=str)
    except Exception:
        evidence_json = '{}'

    with _db() as conn:
        conn.execute("""
            INSERT INTO scans (
                id, url, domain, scanned_at, analysis_mode, access_strategy,
                overall_confidence, primary_font, all_fonts, primary_color,
                color_palette, spacing_base_unit, motion_strategy, motion_durations,
                content_density_pct, brand_personality, consistency_score,
                page_type, layout_pattern, css_sophistication, evidence_json, notes
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                url=excluded.url, scanned_at=excluded.scanned_at,
                overall_confidence=excluded.overall_confidence,
                primary_font=excluded.primary_font, all_fonts=excluded.all_fonts,
                primary_color=excluded.primary_color, color_palette=excluded.color_palette,
                spacing_base_unit=excluded.spacing_base_unit,
                motion_strategy=excluded.motion_strategy, motion_durations=excluded.motion_durations,
                content_density_pct=excluded.content_density_pct,
                brand_personality=excluded.brand_personality,
                consistency_score=excluded.consistency_score,
                page_type=excluded.page_type, layout_pattern=excluded.layout_pattern,
                css_sophistication=excluded.css_sophistication,
                evidence_json=excluded.evidence_json,
                notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE notes END
        """, [
            scan_id, url, domain, time.time(), analysis_mode, access_strategy,
            overall_conf,
            indexed['primary_font'], indexed['all_fonts'], indexed['primary_color'],
            indexed['color_palette'], indexed['spacing_base_unit'],
            indexed['motion_strategy'], indexed['motion_durations'],
            indexed['content_density_pct'], indexed['brand_personality'],
            indexed['consistency_score'], indexed['page_type'],
            indexed['layout_pattern'], indexed['css_sophistication'],
            evidence_json, notes or '',
        ])

    logger.info(f"Saved scan {scan_id} for {url}")
    return scan_id


def list_scans(
    domain: str = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict]:
    """
    Return a list of saved scans (summary only — no full evidence).

    Args:
        domain: Filter by domain (e.g. 'polyesterzine.com').
        limit:  Page size.
        offset: Pagination offset.
    """
    with _db() as conn:
        where = 'WHERE domain = ?' if domain else ''
        params = [domain] if domain else []
        params += [limit, offset]
        rows = conn.execute(f"""
            SELECT id, url, domain, scanned_at, analysis_mode, overall_confidence,
                   primary_font, primary_color, spacing_base_unit,
                   motion_strategy, content_density_pct, brand_personality,
                   consistency_score, page_type, layout_pattern, css_sophistication,
                   color_palette, notes
            FROM scans
            {where}
            ORDER BY scanned_at DESC
            LIMIT ? OFFSET ?
        """, params).fetchall()
        return [dict(r) for r in rows]


def get_scan(scan_id: str) -> Optional[Dict]:
    """Return a single scan including full evidence_json."""
    with _db() as conn:
        row = conn.execute(
            'SELECT * FROM scans WHERE id = ?', [scan_id]
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result['evidence'] = json.loads(result.pop('evidence_json', '{}'))
        except Exception:
            result['evidence'] = {}
        return result


def delete_scan(scan_id: str) -> bool:
    """Delete a scan and all its findings."""
    with _db() as conn:
        conn.execute('DELETE FROM scans WHERE id = ?', [scan_id])
        return conn.execute('SELECT changes()').fetchone()[0] > 0


def search_scans(
    query: Dict,
    limit: int = 20,
) -> List[Dict]:
    """
    Search saved scans by design property.

    Args:
        query: Dict with any combination of:
            primary_font      — exact or LIKE match ('Playfair%')
            primary_color     — exact hex ('#000000')
            motion_strategy   — 'minimal'|'performance-conscious'|'layered'|'expressive'
            spacing_base_unit — e.g. '4px'
            page_type         — e.g. 'singleArticle', 'contentGrid'
            brand_personality — LIKE match
            min_confidence    — minimum overall_confidence
            max_confidence    — maximum overall_confidence
            domain            — exact domain match

    Returns:
        List of matching scan summaries.
    """
    clauses = []
    params  = []

    mappings = {
        'primary_font':    ('primary_font',    'LIKE'),
        'primary_color':   ('primary_color',   '='),
        'motion_strategy': ('motion_strategy', '='),
        'spacing_base_unit': ('spacing_base_unit', '='),
        'page_type':       ('page_type',       '='),
        'brand_personality': ('brand_personality', 'LIKE'),
        'domain':          ('domain',          '='),
        'layout_pattern':  ('layout_pattern',  'LIKE'),
    }
    for key, (col, op) in mappings.items():
        val = query.get(key)
        if val is not None:
            clauses.append(f'{col} {op} ?')
            params.append(val)

    if 'min_confidence' in query:
        clauses.append('overall_confidence >= ?')
        params.append(query['min_confidence'])
    if 'max_confidence' in query:
        clauses.append('overall_confidence <= ?')
        params.append(query['max_confidence'])

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    params.append(limit)

    with _db() as conn:
        rows = conn.execute(f"""
            SELECT id, url, domain, scanned_at, analysis_mode, overall_confidence,
                   primary_font, primary_color, spacing_base_unit,
                   motion_strategy, content_density_pct, brand_personality,
                   consistency_score, page_type, layout_pattern, css_sophistication,
                   color_palette, notes
            FROM scans
            {where}
            ORDER BY scanned_at DESC
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]


def get_library_stats() -> Dict:
    """Return aggregate stats across all scans — the cross-scan patterns."""
    with _db() as conn:
        total  = conn.execute('SELECT COUNT(*) FROM scans').fetchone()[0]
        domains = conn.execute('SELECT COUNT(DISTINCT domain) FROM scans').fetchone()[0]

        # Most common fonts
        fonts = conn.execute("""
            SELECT primary_font, COUNT(*) as n
            FROM scans WHERE primary_font IS NOT NULL
            GROUP BY primary_font ORDER BY n DESC LIMIT 10
        """).fetchall()

        # Motion strategy distribution
        strategies = conn.execute("""
            SELECT motion_strategy, COUNT(*) as n
            FROM scans WHERE motion_strategy IS NOT NULL
            GROUP BY motion_strategy ORDER BY n DESC
        """).fetchall()

        # Average confidence by domain
        by_domain = conn.execute("""
            SELECT domain, COUNT(*) as scans,
                   ROUND(AVG(overall_confidence), 1) as avg_confidence,
                   MAX(scanned_at) as last_scanned
            FROM scans
            GROUP BY domain ORDER BY last_scanned DESC LIMIT 20
        """).fetchall()

        # Spacing base unit distribution
        spacing = conn.execute("""
            SELECT spacing_base_unit, COUNT(*) as n
            FROM scans WHERE spacing_base_unit IS NOT NULL
            GROUP BY spacing_base_unit ORDER BY n DESC LIMIT 5
        """).fetchall()

        # Findings count
        findings = conn.execute('SELECT COUNT(*) FROM findings').fetchone()[0]

    return {
        'total_scans':    total,
        'unique_domains': domains,
        'total_findings': findings,
        'common_fonts':   [{'font': r['primary_font'], 'count': r['n']} for r in fonts],
        'motion_strategies': [{'strategy': r['motion_strategy'], 'count': r['n']} for r in strategies],
        'by_domain':      [dict(r) for r in by_domain],
        'spacing_units':  [{'unit': r['spacing_base_unit'], 'count': r['n']} for r in spacing],
    }


# ── Findings (swipe file) ─────────────────────────────────────────────────────

def save_finding(
    scan_id: str,
    scan_url: str,
    section_data: Dict,
    label: str = '',
    tags: List[str] = None,
    notes: str = '',
    section_index: int = None,
) -> str:
    """
    Save a specific section/component as a finding (swipe file entry).

    Args:
        scan_id:       ID of the parent scan.
        scan_url:      URL of the scanned page (for display).
        section_data:  The dwell panel data (rect, styles, blueprint, etc.).
        label:         User-provided label (e.g. "Membership promo layout").
        tags:          Tag list (e.g. ['zine', 'membership', 'hero']).
        notes:         Free-text notes.
        section_index: Index into the attention flow (0-based).

    Returns:
        finding_id string.
    """
    finding_id = str(uuid.uuid4())
    with _db() as conn:
        conn.execute("""
            INSERT INTO findings (id, scan_id, scan_url, saved_at, label, tags, notes,
                                  section_index, section_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            finding_id, scan_id, scan_url, time.time(),
            label or '', json.dumps(tags or []), notes or '',
            section_index, json.dumps(section_data, default=str),
        ])
    return finding_id


def list_findings(
    tag: str = None,
    scan_id: str = None,
    limit: int = 50,
) -> List[Dict]:
    """List saved findings, optionally filtered by tag or scan."""
    clauses, params = [], []
    if tag:
        clauses.append("json_each.value = ?")
        from_clause = "FROM findings, json_each(findings.tags)"
        params.append(tag)
    else:
        from_clause = "FROM findings"

    if scan_id:
        clauses.append("scan_id = ?")
        params.append(scan_id)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    params.append(limit)

    with _db() as conn:
        rows = conn.execute(f"""
            SELECT findings.id, findings.scan_id, findings.scan_url, findings.saved_at,
                   findings.label, findings.tags, findings.notes,
                   findings.section_index, findings.section_data
            {from_clause}
            {where}
            ORDER BY findings.saved_at DESC
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]


def delete_finding(finding_id: str) -> bool:
    with _db() as conn:
        conn.execute('DELETE FROM findings WHERE id = ?', [finding_id])
        return conn.execute('SELECT changes()').fetchone()[0] > 0


def update_finding_tags(finding_id: str, tags: List[str], label: str = None) -> bool:
    """Update tags (and optionally label) on an existing finding."""
    with _db() as conn:
        if label is not None:
            conn.execute(
                'UPDATE findings SET tags = ?, label = ? WHERE id = ?',
                [json.dumps(tags), label, finding_id]
            )
        else:
            conn.execute(
                'UPDATE findings SET tags = ? WHERE id = ?',
                [json.dumps(tags), finding_id]
            )
        return conn.execute('SELECT changes()').fetchone()[0] > 0


# ── Maintenance ────────────────────────────────────────────────────────────────

def reindex_all_scans() -> Dict:
    """
    Re-run ``_index_evidence`` on every stored scan and update the indexed
    columns in-place.

    Useful after:
      - Adding new indexed properties (e.g. motion_strategy after narrative was wired)
      - Fixing ``_flatten_evidence`` for smart-nav scans
      - Any schema migration that adds new columns

    Also backfills ``motion_strategy`` for scans saved before
    ``_synthesize_motion_narrative`` was wired, using ``_infer_motion_strategy``.

    Returns a summary dict: ``{updated, errors}``.
    """
    updated = errors = 0

    with _db() as conn:
        rows = conn.execute(
            'SELECT id, evidence_json FROM scans ORDER BY scanned_at DESC'
        ).fetchall()

        for row in rows:
            scan_id = row['id']
            try:
                evidence = json.loads(row['evidence_json'] or '{}')
                indexed  = _index_evidence(evidence)

                # Backfill motion_strategy for scans saved before narrative was wired
                if indexed.get('motion_strategy') is None:
                    flat_ev = _flatten_evidence(evidence)
                    inferred = _infer_motion_strategy(flat_ev.get('motion_tokens', {}))
                    indexed['motion_strategy'] = inferred

                # Also pick up overall_confidence from _meta if not already stored
                flat = _flatten_evidence(evidence)
                meta2 = flat.get('_meta', {})
                overall_conf = meta2.get('overall_confidence')

                conn.execute("""
                    UPDATE scans SET
                        primary_font=?,       all_fonts=?,       primary_color=?,
                        color_palette=?,      spacing_base_unit=?,
                        motion_strategy=?,    motion_durations=?,
                        content_density_pct=?, brand_personality=?,
                        consistency_score=?,  page_type=?,
                        layout_pattern=?,     css_sophistication=?,
                        overall_confidence=COALESCE(?, overall_confidence)
                    WHERE id=?
                """, [
                    indexed['primary_font'],       indexed['all_fonts'],
                    indexed['primary_color'],       indexed['color_palette'],
                    indexed['spacing_base_unit'],
                    indexed['motion_strategy'],     indexed['motion_durations'],
                    indexed['content_density_pct'], indexed['brand_personality'],
                    indexed['consistency_score'],   indexed['page_type'],
                    indexed['layout_pattern'],      indexed['css_sophistication'],
                    overall_conf,
                    scan_id,
                ])
                updated += 1
            except Exception as exc:
                logger.warning(f"reindex_all_scans: skipped {scan_id}: {exc}")
                errors += 1

    logger.info(f"reindex_all_scans: updated={updated} errors={errors}")
    return {'updated': updated, 'errors': errors}
