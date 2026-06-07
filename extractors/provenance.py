"""
Provenance tagging utilities for extractor results.

Answers "how do we know this?" for every metric the scraper produces.
Non-destructive — safe to call on any dict that an extractor returns.
All tags live under the '_provenance' key and are ignored by consumers
that don't understand them.

Usage in an extractor::

    from extractors.provenance import tag, Source

    return tag({
        'pattern': 'Inter, system-ui',
        'confidence': 85,
    }, source=Source.COMPUTED_STYLE, method='getComputedStyle.fontFamily')

The stability check in deep_evidence_engine adds these automatically
when page instability is detected — extractor authors don't need to
handle it themselves.
"""

from typing import Optional


# ── Source constants ──────────────────────────────────────────────────────────

class Source:
    """
    Where the value came from.  Use these constants for the ``source`` field
    rather than bare strings — they're searchable and typo-proof.
    """
    DOM_EXTRACTION = 'dom_extraction'   # read from DOM attributes, text, tag structure
    COMPUTED_STYLE = 'computed_style'   # window.getComputedStyle()
    CSS_RULE       = 'css_rule'         # parsed from stylesheet @rules / selector blocks
    CSS_VAR        = 'css_variable'     # CSS custom property (--token: value)
    NETWORK        = 'network'          # HTTP headers, response inspection
    CDP            = 'cdp'              # Chrome DevTools Protocol (CDP domain)
    SYNTHESIZED    = 'synthesized'      # derived/aggregated from multiple signals
    INFERRED       = 'inferred'         # heuristic — not directly observed in the DOM


# ── Core tagging functions ────────────────────────────────────────────────────

def tag(
    result: dict,
    *,
    source: str,
    method: Optional[str] = None,
    verified: bool = False,
    **extra,
) -> dict:
    """
    Attach a ``_provenance`` block to an extractor result dict.

    Args:
        result:   The dict the extractor is about to return.
        source:   One of the ``Source.*`` constants.
        method:   The specific API / CSS property / heuristic used.
                  e.g. ``'getComputedStyle.fontFamily'``, ``'getBoundingClientRect'``.
        verified: True if a second-pass probe confirmed this value.
        **extra:  Any additional fields to include in the provenance block.

    Returns:
        The same ``result`` dict, mutated in-place (also returned for chaining).
    """
    result['_provenance'] = {
        'source':   source,
        'method':   method,
        'verified': verified,
        **extra,
    }
    return result


def mark_inferred(result: dict, reason: str) -> dict:
    """
    Mark a result as inferred (heuristic, not directly observed).

    The caller should also lower ``result['confidence']`` — this function
    only annotates the provenance; it does not touch the confidence value.

    Args:
        result: Extractor result dict.
        reason: Human-readable explanation of why this is an inference.

    Returns:
        The same ``result`` dict, mutated in-place.
    """
    prov = result.get('_provenance', {})
    prov['source']          = Source.INFERRED
    prov['inferred_reason'] = reason
    result['_provenance']   = prov
    return result


def mark_validated(result: dict, *, method: str, original_confidence: int) -> dict:
    """
    Mark a result as validated by a second-pass probe
    (e.g. the color injection test described in the build plan).

    Args:
        result:               Extractor result dict.
        method:               Description of the validation technique used.
        original_confidence:  The confidence value *before* validation, for audit trail.

    Returns:
        The same ``result`` dict, mutated in-place.
    """
    prov = result.get('_provenance', {})
    prov['verified']                 = True
    prov['validation_method']        = method
    prov['pre_validation_confidence'] = original_confidence
    result['_provenance']            = prov
    return result


# ── Stability-downgrade annotation (applied by the engine, not extractors) ───

def mark_stability_downgraded(
    result: dict,
    *,
    downgrade_pts: int,
    stability_ratio: float,
    signals: list,
) -> dict:
    """
    Record that this result's confidence was reduced because the page was
    found to be dynamically unstable (A/B test, rotating banner, etc.).

    Called by ``DeepEvidenceEngine._apply_stability_downgrade()``, not by
    individual extractors.

    Args:
        result:          Extractor result dict (already confidence-downgraded).
        downgrade_pts:   How many confidence points were subtracted.
        stability_ratio: The page similarity ratio that triggered the downgrade.
        signals:         List of instability signals detected.

    Returns:
        The same ``result`` dict, mutated in-place.
    """
    prov = result.get('_provenance', {})
    prov['stability_downgrade'] = {
        'points':  downgrade_pts,
        'ratio':   stability_ratio,
        'signals': signals[:3],          # cap to avoid bloat
        'note':    (
            f'Confidence reduced by {downgrade_pts} pts — page structure '
            f'changed between two DOM snapshots (ratio={stability_ratio:.2f}). '
            'Results may reflect an A/B variant, rotating banner, or personalised content.'
        ),
    }
    result['_provenance'] = prov
    return result


# ── Convenience: get provenance for display / debugging ──────────────────────

def get_source_label(result: dict) -> str:
    """
    Return a short human-readable label for how a metric was derived.
    Safe to call on any dict — returns '' if no provenance is attached.
    """
    prov = result.get('_provenance')
    if not prov:
        return ''
    source = prov.get('source', '')
    verified = prov.get('verified', False)
    labels = {
        Source.DOM_EXTRACTION: 'DOM',
        Source.COMPUTED_STYLE: 'computed',
        Source.CSS_RULE:       'stylesheet',
        Source.CSS_VAR:        'CSS var',
        Source.NETWORK:        'network',
        Source.CDP:            'CDP',
        Source.SYNTHESIZED:    'synthesized',
        Source.INFERRED:       'inferred',
    }
    label = labels.get(source, source)
    if verified:
        label += ' ✓'
    if prov.get('stability_downgrade'):
        label += ' ⚠'
    return label
