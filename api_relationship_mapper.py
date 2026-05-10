"""
API Relationship Mapper - jsoncrack.com-style Visual API Analysis

Analyzes network requests to detect:
1. API endpoint relationships (which calls which)
2. Data flow dependencies (response from A used in B)
3. WebSocket ↔ REST synchronization
4. Redundant/duplicate requests
5. Request chains and sequences

Use case: Instead of showing flat API list, show HOW they're connected
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


class APIRelationshipMapper:
    """
    Analyze API requests to build relationship tree
    """

    def __init__(self, api_requests: List[Dict]):
        """
        Args:
            api_requests: List of API request dicts from network pulse
                Each dict should have: url, method, status, response_body
        """
        self.api_requests = api_requests or []

    def analyze_relationships(self) -> Dict:
        """
        Comprehensive API relationship analysis

        Returns:
            {
                'endpoints': [...],  # Unique API endpoints
                'semantic_classification': {...},  # APIs classified by design role
                'design_insights': {...},  # Human-readable architectural conclusions
                'relationships': [...],  # Connection between APIs
                'data_dependencies': [...],  # Response → Request usage
                'redundant_requests': [...],  # Duplicate calls
                'request_chains': [...],  # Sequential patterns
                'mermaid_diagram': '...',  # Visual diagram code
                'stats': {...}
            }
        """
        endpoints = self._extract_endpoints()
        semantic_map = self._classify_semantic_roles(endpoints)
        design_insights = self._generate_design_insights(semantic_map, endpoints)
        capabilities = self._infer_capabilities(semantic_map, endpoints)
        relationships = self._detect_relationships()
        data_deps = self._find_data_dependencies()
        redundant = self._find_redundant_requests()
        chains = self._identify_request_chains(relationships)

        try:
            mermaid = self._generate_mermaid_diagram(endpoints, relationships)
        except Exception:
            try:
                mermaid = self._generate_simplified_diagram(endpoints)
            except Exception:
                mermaid = self._generate_fallback_diagram(endpoints)

        return {
            'endpoints': endpoints,
            'semantic_classification': semantic_map,
            'design_insights': design_insights,
            'capabilities': capabilities,
            'relationships': relationships,
            'data_dependencies': data_deps,
            'redundant_requests': redundant,
            'request_chains': chains,
            'mermaid_diagram': mermaid,
            'stats': self._calculate_stats(endpoints, relationships, data_deps, redundant),
        }

    # ------------------------------------------------------------------
    # URLPattern-style segment classifier (mirrors deep_evidence_engine.py JS logic)
    # Runs server-side since network requests are captured Python-side.
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_segment(seg: str) -> str:
        """Return the parameter type for a URL path segment."""
        if re.fullmatch(r'\d+', seg):
            return 'id'
        if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', seg, re.I):
            return 'uuid'
        if re.fullmatch(r'v?\d+(\.\d+)+', seg):
            return 'version'
        if re.fullmatch(r'[a-z]{2}(-[A-Z]{2})?', seg):
            return 'locale'
        if re.fullmatch(r'[a-z]{2,8}_[a-zA-Z0-9]+', seg):
            return 'prefixed-id'
        if re.fullmatch(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?', seg):
            return 'slug'
        return 'param'

    @staticmethod
    def _build_template(parts: List[Tuple[str, str]]) -> str:
        """
        Build a URLPattern-style template string from (type, value) parts.
        Suffixes duplicate group names to keep them unique.

        parts: list of (type, value) where type is 'literal'|'id'|'slug'|etc.
        """
        name_count: Dict[str, int] = {}
        segments = []
        for ptype, pval in parts:
            if ptype == 'literal':
                segments.append(pval)
            else:
                base = 'id' if ptype == 'id' else ('key' if ptype == 'prefixed-id' else ptype)
                name_count[base] = name_count.get(base, 0) + 1
                name = base if name_count[base] == 1 else f"{base}{name_count[base]}"
                segments.append(f':{name}(\\d+)' if ptype == 'id' else f':{name}')
        return '/' + '/'.join(segments)

    def _cluster_endpoints(self, raw_endpoints: List[Dict]) -> List[Dict]:
        """
        Group raw (exact-URL) endpoints by inferred URLPattern template.

        /api/users/123   ┐
        /api/users/456   ├─→  GET /api/users/:id(\d+)  call_count=3
        /api/users/789   ┘

        Returns a collapsed list where each entry has a `template` key and
        the original `full_url` / `path` represent the first observed example.
        Endpoints whose paths are unique (no cluster partner) keep their exact URL.
        """
        # Group by (method, depth, host)
        from collections import defaultdict
        groups: Dict[str, List[Dict]] = defaultdict(list)
        for ep in raw_endpoints:
            parsed = urlparse(ep['full_url'])
            segs = [s for s in parsed.path.split('/') if s]
            key = f"{ep['method']}|{parsed.netloc}|{len(segs)}"
            groups[key].append({'ep': ep, 'segs': segs, 'parsed': parsed})

        clustered: List[Dict] = []

        for key, members in groups.items():
            if len(members) < 2:
                # Lone endpoint — keep as-is with an identity template
                ep = members[0]['ep']
                ep['template'] = ep['path']
                ep['example_values'] = {}
                clustered.append(ep)
                continue

            depth = len(members[0]['segs'])
            # For each segment position: literal if all same, else classify by dominant type
            parts: List[Tuple[str, str]] = []
            for i in range(depth):
                vals = [m['segs'][i] for m in members if i < len(m['segs'])]
                unique_vals = list(dict.fromkeys(vals))  # preserve order, dedup
                if len(unique_vals) == 1:
                    parts.append(('literal', unique_vals[0]))
                else:
                    types = [self._classify_segment(v) for v in vals]
                    # Dominant type by frequency
                    type_counts: Dict[str, int] = {}
                    for t in types:
                        type_counts[t] = type_counts.get(t, 0) + 1
                    dominant = max(type_counts, key=type_counts.__getitem__)
                    parts.append((dominant, unique_vals[0]))

            template = self._build_template(parts)

            # Sub-cluster: find the FIRST variable position that has a small set of
            # distinct slug-like values (e.g. pos1="products"/"customers" after literal pos0="v1").
            # Split members by that pivot so each resource type gets its own entry.
            split_pos = None
            split_vals: List[str] = []
            for i in range(depth):
                seg_vals = [m['segs'][i] for m in members if i < len(m['segs'])]
                seg_unique = list(dict.fromkeys(seg_vals))
                seg_all_slugs = all(re.fullmatch(r'[a-z0-9][a-z0-9-]*', v) for v in seg_unique)
                seg_few = 2 <= len(seg_unique) <= max(2, int(len(members) * 0.6))
                if seg_all_slugs and seg_few:
                    split_pos = i
                    split_vals = seg_unique
                    break  # use the first qualifying pivot position

            if depth >= 2 and split_pos is not None:
                sub_groups: Dict[str, List] = defaultdict(list)
                for m in members:
                    pivot = m['segs'][split_pos] if split_pos < len(m['segs']) else '__other__'
                    sub_groups[pivot].append(m)
                for prefix, sub_members in sub_groups.items():
                    if len(sub_members) < 2:
                        ep = sub_members[0]['ep']
                        ep['template'] = ep['path']
                        ep['example_values'] = {}
                        clustered.append(ep)
                        continue
                    sub_parts: List[Tuple[str, str]] = []
                    for i in range(depth):
                        vals = [m['segs'][i] for m in sub_members if i < len(m['segs'])]
                        unique_vals = list(dict.fromkeys(vals))
                        if len(unique_vals) == 1:
                            sub_parts.append(('literal', unique_vals[0]))
                        else:
                            types = [self._classify_segment(v) for v in vals]
                            type_counts = {}
                            for t in types:
                                type_counts[t] = type_counts.get(t, 0) + 1
                            dominant = max(type_counts, key=type_counts.__getitem__)
                            sub_parts.append((dominant, unique_vals[0]))
                    sub_template = self._build_template(sub_parts)
                    # Merge all sub-member endpoints into one clustered entry
                    merged = sub_members[0]['ep'].copy()
                    merged['template'] = sub_template
                    merged['call_count'] = sum(m['ep'].get('call_count', 1) for m in sub_members)
                    total_success = sum(m['ep'].get('success_rate', 0) for m in sub_members)
                    merged['success_rate'] = round(total_success / len(sub_members))
                    # Collect example values for each named param position
                    named_positions = [(i, p[0]) for i, p in enumerate(sub_parts) if p[0] != 'literal']
                    examples: Dict[str, List[str]] = {}
                    for m in sub_members[:3]:
                        for idx, ptype in named_positions:
                            if idx < len(m['segs']):
                                base = 'id' if ptype == 'id' else ('key' if ptype == 'prefixed-id' else ptype)
                                examples.setdefault(base, []).append(m['segs'][idx])
                    merged['example_values'] = {k: list(dict.fromkeys(v))[:3] for k, v in examples.items()}
                    merged['clustered_count'] = len(sub_members)
                    clustered.append(merged)
            else:
                # Merge all members into one clustered entry
                merged = members[0]['ep'].copy()
                merged['template'] = template
                merged['call_count'] = sum(m['ep'].get('call_count', 1) for m in members)
                total_success = sum(m['ep'].get('success_rate', 0) for m in members)
                merged['success_rate'] = round(total_success / len(members))
                named_positions = [(i, p[0]) for i, p in enumerate(parts) if p[0] != 'literal']
                examples: Dict[str, List[str]] = {}
                for m in members[:3]:
                    for idx, ptype in named_positions:
                        if idx < len(m['segs']):
                            base = 'id' if ptype == 'id' else ('key' if ptype == 'prefixed-id' else ptype)
                            examples.setdefault(base, []).append(m['segs'][idx])
                merged['example_values'] = {k: list(dict.fromkeys(v))[:3] for k, v in examples.items()}
                merged['clustered_count'] = len(members)
                clustered.append(merged)

        return clustered

    def _extract_endpoints(self) -> List[Dict]:
        """
        Extract unique API endpoints with metadata, then cluster by inferred
        URLPattern template so /api/users/123 + /api/users/456 → one entry.
        """
        endpoint_map = {}
        for req in self.api_requests:
            url = req.get('url', '')
            if not url:
                continue
            method = req.get('method', 'GET')
            endpoint_key = f"{method} {url}"
            if endpoint_key not in endpoint_map:
                parsed = urlparse(url)
                path = parsed.path
                endpoint_map[endpoint_key] = {
                    'full_url': url,
                    'path': path,
                    'method': method,
                    'call_count': 0,
                    'status': req.get('status', 200),
                    'success_rate': 0,
                    'timestamp': req.get('timestamp', 0),
                }
            ep = endpoint_map[endpoint_key]
            ep['call_count'] += 1
            status = req.get('status', 200)
            if 200 <= status < 400:
                ep['success_rate'] = min(100, ep['success_rate'] + 1)

        raw = list(endpoint_map.values())
        # Cluster exact-URL endpoints into parametric templates
        return self._cluster_endpoints(raw)

    def _classify_semantic_roles(self, endpoints: List[Dict]) -> Dict:
        """
        Classify APIs by design role — matches on path keywords, path prefixes,
        and domain patterns (for third-party analytics/tracking services).
        """
        PATTERNS = {
            'authentication': {
                'keywords': ['auth', 'login', 'logout', 'token', 'oauth', 'session', 'jwt', 'signup', 'register', 'password'],
                'paths': ['/auth', '/login', '/logout', '/token', '/signup'],
                'domains': [],
            },
            'content': {
                'keywords': ['article', 'post', 'blog', 'content', 'page', 'story', 'news', 'feed', 'cms'],
                'paths': ['/articles', '/posts', '/content', '/pages', '/stories'],
                'domains': [],
            },
            'user': {
                'keywords': ['user', 'profile', 'account', 'me', 'member', 'preferences'],
                'paths': ['/users', '/profile', '/me', '/account'],
                'domains': [],
            },
            'monetization': {
                'keywords': ['paywall', 'subscription', 'offer', 'payment', 'billing', 'plan', 'price', 'checkout', 'cart', 'order', 'invoice'],
                'paths': ['/subscribe', '/billing', '/plans', '/offers', '/checkout', '/cart'],
                'domains': [],
            },
            'interaction': {
                'keywords': ['comment', 'like', 'share', 'follow', 'vote', 'react', 'reply', 'notification'],
                'paths': ['/comments', '/likes', '/reactions', '/notifications'],
                'domains': [],
            },
            'search': {
                'keywords': ['search', 'query', 'find', 'suggest', 'autocomplete', 'typeahead'],
                'paths': ['/search', '/query', '/suggest', '/autocomplete'],
                'domains': [],
            },
            'analytics': {
                'keywords': ['collect', 'track', 'event', 'beacon', 'pixel', 'pageview', 'page_view', 'impression', 'analytics', 'telemetry', 'metrics', 'log', 'ingest'],
                'paths': ['/collect', '/track', '/events', '/beacon', '/pixel', '/ingest', '/activity'],
                'domains': ['google-analytics', 'googletagmanager', 'analytics', 'segment', 'mixpanel', 'amplitude', 'hotjar', 'fullstory', 'heap', 'sentry', 'datadoghq', 'newrelic', 'marketo', 'hubspot'],
            },
            'config': {
                'keywords': ['config', 'settings', 'cookie', 'consent', 'enforcement', 'initialize', 'bootstrap', 'manifest'],
                'paths': ['/config', '/settings', '/cookie-settings', '/consent'],
                'domains': ['onetrust', 'cookiebot', 'trustarc'],
            },
            'feature_flags': {
                'keywords': ['flag', 'experiment', 'variant', 'feature', 'ab', 'cohort', 'split', 'toggle'],
                'paths': ['/flags', '/experiments', '/features', '/splits'],
                'domains': ['launchdarkly', 'optimizely', 'split.io', 'statsig', 'flagsmith'],
            },
            'advertising': {
                'keywords': ['ads', 'advert', 'campaign', 'attribution', 'conversion', 'retarget', 'remarketing', 'ddm', 'fls'],
                'paths': ['/ads', '/attribution', '/conversion', '/ddm'],
                'domains': ['doubleclick', 'googlesyndication', 'googleads', 'facebook.com/tr', 'ads.linkedin', 'bat.bing', 'ad.doubleclick'],
            },
        }

        classified: Dict[str, List] = {cat: [] for cat in PATTERNS}
        classified['unclassified'] = []

        for endpoint in endpoints:
            full_url = endpoint.get('full_url', '')
            url_lower = full_url.lower()
            # Prefer the inferred template for path matching — it strips concrete IDs
            # so "/api/v2/users/:id(\d+)" matches 'users' more reliably than "/api/v2/users/12345"
            path = endpoint.get('template', endpoint.get('path', '')).lower()
            matches = []

            for category, patterns in PATTERNS.items():
                kw_score = sum(1 for kw in patterns['keywords'] if kw in url_lower)
                path_score = sum(1 for p in patterns['paths'] if path.startswith(p))
                domain_score = sum(1 for d in patterns.get('domains', []) if d in url_lower)

                total = kw_score + path_score * 2 + domain_score * 3
                # Match if: any path prefix matches, or domain matches, or 1+ keyword matches
                if path_score >= 1 or domain_score >= 1 or kw_score >= 1:
                    matches.append((category, total))

            if matches:
                best = sorted(matches, key=lambda x: x[1], reverse=True)[0][0]
                confidence = min(95, 50 + len(matches) * 15)
                classified[best].append({**endpoint, 'confidence': confidence})
            else:
                classified['unclassified'].append({**endpoint, 'confidence': 1})

        return {cat: apis for cat, apis in classified.items() if apis}

    def _generate_design_insights(self, semantic_map: Dict, endpoints: List[Dict]) -> Dict:
        """
        Generate human-readable architectural insights from semantic classification
        """
        insights = {}

        state_apis = semantic_map.get('authentication', {})
        if state_apis:
            has_jwt = any('jwt' in e.get('path', '') or 'token' in e.get('path', '') for e in state_apis)
            has_session = any('session' in e.get('path', '') for e in state_apis)
            has_me = any('/me' in e.get('path', '') for e in state_apis)
            if has_jwt:
                insights['auth_strategy'] = 'JWT-based stateless authentication'
            elif has_session:
                insights['auth_strategy'] = 'Server-side session management'
            if has_me:
                insights.setdefault('notes', []).append('User identity endpoint detected')
            insights.setdefault('notes', []).append('Authentication mechanism present')

        content_model_apis = semantic_map.get('content', [])
        if content_model_apis:
            entities = [e.get('path', '').split('/')[1] for e in content_model_apis if e.get('path', '').count('/') >= 1]
            entities = [e for e in entities if e]
            if entities:
                insights['content_model'] = 'Content model centers on: ' + ', '.join(set(entities))

        interaction_apis = semantic_map.get('interaction', [])
        if interaction_apis:
            insights['interaction_model'] = f'{len(interaction_apis)} interactive API endpoint(s) detected'

        monetization_apis = semantic_map.get('monetization', [])
        if monetization_apis:
            has_paywall = any('paywall' in e.get('path', '') for e in monetization_apis)
            has_subscription = any('subscription' in e.get('path', '') for e in monetization_apis)
            has_offer = any('offer' in e.get('path', '') for e in monetization_apis)
            if has_paywall or has_subscription or has_offer:
                insights['monetization'] = 'Metered paywall / subscription strategy detected'

        feature_flag_apis = semantic_map.get('feature_flags', [])
        if feature_flag_apis:
            has_flag = any('flag' in e.get('path', '') for e in feature_flag_apis)
            has_experiment = any('experiment' in e.get('path', '') for e in feature_flag_apis)
            if has_flag or has_experiment:
                insights['feature_flags'] = 'A/B testing or feature flag system detected'

        # Most-used category
        category_counts = {
            cat: sum(e.get('call_count', 1) for e in data)
            for cat, data in semantic_map.items()
            if cat != 'unclassified' and data
        }
        if category_counts:
            dominant = max(category_counts, key=lambda k: category_counts[k])
            insights['dominant_category'] = f'{dominant} APIs dominate traffic'

        return insights

    def _detect_relationships(self) -> List[Dict]:
        """
        Detect relationships between API endpoints
        """
        relationships = []
        sorted_requests = sorted(self.api_requests, key=lambda r: r.get('timestamp', 0))

        for i, req_a in enumerate(sorted_requests):
            for req_b in sorted_requests[i+1:i+6]:
                url_a = req_a.get('url', '')
                url_b = req_b.get('url', '')
                if not url_a or not url_b or url_a == url_b:
                    continue
                time_diff = req_b.get('timestamp', 0) - req_a.get('timestamp', 0)
                if time_diff < 0:
                    continue
                if time_diff < 50:
                    rel_type = 'parallel'
                elif time_diff < 500:
                    rel_type = 'sequential'
                else:
                    continue
                relationships.append({
                    'from': url_a,
                    'to': url_b,
                    'type': rel_type,
                    'time_gap_ms': time_diff,
                })
                if len(relationships) >= 100:
                    break

        return relationships

    def _find_data_dependencies(self) -> List[Dict]:
        """
        Find cases where response from API A is used in request to API B
        """
        dependencies = []
        for i, req_a in enumerate(self.api_requests):
            response_a = req_a.get('response_body', '')
            if not response_a:
                continue
            try:
                response_data = json.loads(response_a)
            except Exception as e:
                logging.debug(f'Could not parse API response (skipping): {e}')
                continue

            extracted_ids = self._extract_ids(response_data)
            for req_b in self.api_requests[i+1:]:
                url_b = req_b.get('url', '')
                body_b = req_b.get('request_body', '')
                for id_val in extracted_ids:
                    if str(id_val) in url_b or (body_b and str(id_val) in body_b):
                        dependencies.append({
                            'source_url': req_a.get('url', ''),
                            'target_url': url_b,
                            'shared_id': id_val,
                            'confidence': 'ID',
                            'confidence_pct': 95,
                        })
                        break

        return dependencies

    def _extract_ids(self, data, prefix: str = '') -> List:
        """
        Recursively extract potential ID fields from JSON data
        """
        ids = []
        id_fields = ('id', 'userId', 'user_id', 'postId', 'post_id', 'articleId', 'token')
        if isinstance(data, dict):
            for id_field in (k for k in data if k in id_fields):
                value = data[id_field]
                if isinstance(value, (str, int)) and len(str(value)) >= 3 and '.' not in str(value):
                    ids.append(value)
            for v in data.values():
                ids.extend(self._extract_ids(v, prefix))
        elif isinstance(data, list):
            for item in data[:5]:
                ids.extend(self._extract_ids(item, prefix))
        return ids

    def _find_redundant_requests(self) -> List[Dict]:
        """
        Find duplicate or redundant API calls
        """
        redundant = []
        url_groups: Dict[str, List] = {}
        for req in self.api_requests:
            url = req.get('url', '')
            if not url:
                continue
            url_groups.setdefault(url, []).append(req)

        for url, reqs in url_groups.items():
            if len(reqs) > 1:
                redundant.append({
                    'url': url,
                    'call_count': len(reqs),
                    'type': 'duplicate',
                    'wasted_calls': len(reqs) - 1,
                    'suggestion': 'Cache response or debounce calls',
                })

        return redundant

    def _identify_request_chains(self, relationships: List[Dict]) -> List[List[str]]:
        """
        Identify sequential request chains (A → B → C → D)
        """
        sequential = {r['from']: r['to'] for r in relationships if r.get('type') == 'sequential'}
        chains = []
        visited = set()

        def dfs(url, current_chain):
            if url in visited or len(current_chain) > 6:
                return
            visited.add(url)
            current_chain.append(url)
            next_url = sequential.get(url)
            if next_url:
                dfs(next_url, current_chain)
            elif len(current_chain) >= 2:
                chains.append(current_chain[:])
            current_chain.pop()

        for url in sequential:
            dfs(url, [])

        return [chain for chain in chains if len(chain) >= 2]

    def _generate_mermaid_diagram(self, endpoints: List[Dict], relationships: List[Dict]) -> str:
        """
        Generate Mermaid.js diagram code for visualization with robust error handling
        """
        if len(endpoints) > 15:
            return self._generate_simplified_diagram(endpoints)

        mermaid = 'graph TD\n'
        node_map = {}
        for i, endpoint in enumerate(endpoints):
            node_id = f'API{i}'
            node_map[endpoint.get('full_url', '')] = node_id
            method = endpoint.get('method', 'GET')
            # Prefer template over raw path — shows :id instead of 12345
            path = endpoint.get('template', endpoint.get('path', endpoint.get('full_url', '')))[-40:]
            count = endpoint.get('call_count', 1)
            clustered = endpoint.get('clustered_count', 1)
            label = path.replace('"', "'").replace('[', '(').replace(']', ')')
            # Show "×N calls [M URLs]" when clustered to make the collapsing visible
            count_str = f'×{count}' if clustered <= 1 else f'×{count} [{clustered} URLs]'
            mermaid += f'    {node_id}["{method}: {label} {count_str}"]\n'

        for rel in relationships[:20]:
            from_id = node_map.get(rel.get('from', ''))
            to_id = node_map.get(rel.get('to', ''))
            if from_id and to_id:
                rel_type = rel.get('type', '')
                arrow = '-->' if rel_type == 'sequential' else '-.->'
                mermaid += f'    {from_id} {arrow} {to_id}\n'

        return mermaid

    def _generate_simplified_diagram(self, endpoints: List[Dict]) -> str:
        """Generate simplified diagram for complex APIs"""
        mermaid = 'graph TD\n'
        mermaid += '    START[API Calls]\n'
        methods: Dict[str, List] = {}
        for endpoint in endpoints:
            method = endpoint.get('method', 'METHOD')
            methods.setdefault(method, []).append(endpoint)
        for i, (method, eps) in enumerate(methods.items()):
            count = sum(e.get('call_count', 1) for e in eps)
            label = f'{method}: {len(eps)} endpoints, {count} calls'
            mermaid += f'    M{i}["{label}"]\n'
            mermaid += f'    START --> M{i}\n'
        return mermaid

    def _generate_fallback_diagram(self, endpoints: List[Dict]) -> str:
        """Fallback when mermaid generation fails"""
        mermaid = 'graph TD\n'
        mermaid += f'    A[Detected {len(endpoints)} API endpoints]\n'
        methods = list({e.get('method', '') for e in endpoints})
        for i, method in enumerate(methods[:5]):
            eps = [e for e in endpoints if e.get('method') == method]
            count = sum(e.get('call_count', 1) for e in eps)
            mermaid += f'    B{i}["{method}: {count} calls"]\n'
            mermaid += f'    A --> B{i}\n'
        return mermaid

    def _infer_capabilities(self, semantic_map: Dict, endpoints: List[Dict]) -> Dict:
        """
        Translate endpoint map → plain-language capability statements.

        Groups what the site *can do* into human-readable bullets so that
        an LLM consumer (or designer) can read this without parsing raw paths.

        Returns:
            {
              'summary': str,              # 1-sentence site characterization
              'can_do': [str],             # plain-language capability bullets
              'requires_auth': [str],      # categories that seem auth-gated
              'public_actions': [str],     # categories accessible without auth
              'detected_features': {str: bool},  # feature flags
              'recommended_use_cases': [str],    # practical suggestions
            }
        """
        cats = set(semantic_map.keys()) - {'unclassified'}

        has_auth         = 'authentication'  in cats
        has_content      = 'content'         in cats
        has_user         = 'user'            in cats
        has_search       = 'search'          in cats
        has_interaction  = 'interaction'     in cats
        has_monetization = 'monetization'    in cats
        has_analytics    = 'analytics'       in cats
        has_flags        = 'feature_flags'   in cats
        has_ads          = 'advertising'     in cats
        has_config       = 'config'          in cats

        # Detect realtime (WebSocket hints in URLs)
        has_realtime = any(
            'ws' in ep.get('full_url', '') or 'socket' in ep.get('full_url', '') or
            'push' in ep.get('full_url', '') or 'stream' in ep.get('full_url', '')
            for ep in endpoints
        )

        # ── Capability bullets ────────────────────────────────────────────
        can_do: List[str] = []
        public_actions: List[str] = []
        requires_auth: List[str] = []

        if has_content:
            can_do.append("Read and browse content (articles, posts, or catalog items)")
            public_actions.append('content')
        if has_search:
            can_do.append("Search and filter content via API")
            public_actions.append('search')
        if has_auth:
            if has_user:
                can_do.append("Create and manage user accounts (sign up, sign in, profile)")
            else:
                can_do.append("Authenticate users (login / token-based)")
        if has_interaction:
            can_do.append("Social interactions: likes, comments, follows, reactions (auth likely required)")
            requires_auth.append('interaction')
        if has_monetization:
            can_do.append("Monetize via subscriptions or paywall (checkout, billing)")
            requires_auth.append('monetization')
        if has_realtime:
            can_do.append("Deliver real-time updates (WebSocket or streaming)")
        if has_flags:
            can_do.append("Run A/B experiments and feature flags")
        if has_analytics:
            can_do.append("Track user behavior with analytics/telemetry (passive, no auth needed)")
            public_actions.append('analytics')

        # ── Site characterization summary ─────────────────────────────────
        # Infer site archetype from dominant category combo
        if has_content and has_monetization and has_interaction:
            archetype = "a subscription media platform with social features"
        elif has_content and has_interaction and not has_monetization:
            archetype = "a social content platform"
        elif has_content and has_monetization and not has_interaction:
            archetype = "a paywalled content site"
        elif has_content and has_search and not has_interaction:
            archetype = "a searchable content or documentation site"
        elif has_monetization and not has_content:
            archetype = "an e-commerce or SaaS billing platform"
        elif has_user and has_auth and not has_content:
            archetype = "an authenticated app or dashboard"
        elif has_content and not has_auth:
            archetype = "a read-only public content site"
        elif cats:
            archetype = f"a site with {', '.join(list(cats)[:3])} capabilities"
        else:
            archetype = "a website with limited detectable API surface"

        summary = f"This appears to be {archetype}."
        if has_auth:
            summary += " Authentication is required for personalized features."
        if has_flags:
            summary += " Feature flags suggest active A/B testing infrastructure."

        # ── Recommended use cases ─────────────────────────────────────────
        use_cases: List[str] = []
        if has_content and not has_auth:
            use_cases.append("Read-only content scraping or indexing (no auth required)")
        if has_search:
            use_cases.append("Search API integration for content discovery")
        if has_auth and has_content:
            use_cases.append("Authenticated content access (requires valid session/token)")
        if has_realtime:
            use_cases.append("Real-time feed subscription (WebSocket listener)")
        if not use_cases:
            use_cases.append("Inspect network traffic for undocumented API surface")

        # ── Probable undiscovered endpoints ──────────────────────────────────
        # When versioned REST paths are visible (e.g. /api/v2/live, /api/v2/mixtapes),
        # the namespace likely has more resources than the page happened to call.
        # Infer probable siblings from the API base + common REST resource names
        # for this site archetype — surfaces things like /api/v2/shows, /api/v2/artists
        # that only get called on pages we haven't scanned yet.
        probable_endpoints: List[Dict] = []
        seen_api_bases: set = set()

        for ep in endpoints:
            full_url = ep.get('full_url', '')
            parsed   = urlparse(full_url)
            path     = parsed.path

            # Find versioned API base: /api/v1/, /api/v2/, /v1/, /v2/, etc.
            m = re.match(r'^((?:/[^/]+)?/(?:api/)?v\d+)', path)
            if not m:
                continue
            api_base = f"{parsed.scheme}://{parsed.netloc}{m.group(1)}"
            if api_base in seen_api_bases:
                continue
            seen_api_bases.add(api_base)

            # Resource names that are actually called
            called_resources: set = set()
            for e2 in endpoints:
                p2 = urlparse(e2.get('full_url', '')).path
                if p2.startswith(m.group(1)):
                    # Extract first segment after the base
                    rest = p2[len(m.group(1)):].strip('/')
                    resource = rest.split('/')[0].split('?')[0]
                    if resource and not resource.isdigit():
                        called_resources.add(resource)

            # Archetype-specific probable siblings
            archetype_resources: Dict[str, List[str]] = {
                'subscription media platform':  ['shows', 'artists', 'episodes', 'playlists', 'genres', 'users'],
                'paywalled content site':       ['shows', 'artists', 'episodes', 'collections', 'users'],
                'social content platform':      ['users', 'posts', 'comments', 'feeds', 'follows'],
                'searchable content or documentation site': ['search', 'docs', 'articles', 'categories'],
                'e-commerce or SaaS billing platform': ['products', 'orders', 'customers', 'plans'],
                'authenticated app or dashboard': ['users', 'accounts', 'settings', 'dashboard'],
                'read-only public content site': ['posts', 'pages', 'categories', 'tags'],
            }
            probable_siblings = archetype_resources.get(archetype, ['search', 'users', 'content'])

            for resource in probable_siblings:
                if resource in called_resources:
                    continue  # Already observed — not a gap
                probable_url = f"{api_base}/{resource}"
                probable_endpoints.append({
                    'url': probable_url,
                    'resource': resource,
                    'confidence': 'medium',
                    'rationale': (
                        f"Inferred from API namespace {m.group(1)!r}. "
                        f"Observed resources: {sorted(called_resources)}. "
                        f"Common for {archetype}."
                    ),
                    'how_to_verify': f"Open DevTools → Network tab → navigate to a {resource} page and filter for {m.group(1)}/{resource}",
                })

        return {
            'summary': summary,
            'can_do': can_do,
            'requires_auth': list(dict.fromkeys(requires_auth)),
            'public_actions': list(dict.fromkeys(public_actions)),
            'detected_features': {
                'authentication': has_auth,
                'content_api': has_content,
                'search': has_search,
                'social_interactions': has_interaction,
                'monetization': has_monetization,
                'realtime': has_realtime,
                'feature_flags': has_flags,
                'analytics_tracking': has_analytics,
                'advertising': has_ads,
                'consent_config': has_config,
            },
            'recommended_use_cases': use_cases,
            'probable_undiscovered_endpoints': probable_endpoints[:12],
        }

    def _calculate_stats(self, endpoints, relationships, data_deps, redundant) -> Dict:
        """
        Calculate overall statistics
        """
        total_requests = sum(e.get('call_count', 0) for e in endpoints)
        unique_endpoints = len(endpoints)
        total_relationships = len(relationships)
        wasted = sum(r.get('wasted_calls', 0) for r in redundant)
        efficiency = round(max(0, 100 - (wasted / max(total_requests, 1) * 100)), 1)
        return {
            'total_requests': total_requests,
            'unique_endpoints': unique_endpoints,
            'total_relationships': total_relationships,
            'data_dependencies': len(data_deps),
            'redundant_calls': len(redundant),
            'wasted_requests': wasted,
            'efficiency_score': efficiency,
        }
