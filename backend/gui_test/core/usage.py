"""Adapter-reported cumulative usage. Never derive billing from terminal text."""
from decimal import Decimal, InvalidOperation


def normalize_usage(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Usage must be a bounded list of model totals')
    rows, seen = [], set()
    for row in value:
        if not isinstance(row, dict):
            raise ValueError('Invalid usage record')
        provider, model = row.get('provider'), row.get('model')
        if any(not isinstance(x, str) or not x.strip() or len(x) > 160 for x in (provider, model)):
            raise ValueError('Usage requires provider and model')
        if (provider, model) in seen:
            raise ValueError('Duplicate model usage')
        seen.add((provider, model))
        clean = {'provider': provider, 'model': model}
        for field in ('input_tokens', 'output_tokens'):
            n = row.get(field)
            if n is not None and (type(n) is not int or not 0 <= n <= 10**15):
                raise ValueError('Invalid token count')
            clean[field] = n
        cost = row.get('cost_usd')
        if cost is not None:
            try:
                cost = Decimal(str(cost))
            except InvalidOperation as exc:
                raise ValueError('Invalid cost') from exc
            if not cost.is_finite() or not 0 <= cost <= 10**9:
                raise ValueError('Invalid cost')
            cost = str(cost)
        clean['cost_usd'] = cost
        rows.append(clean)
    return rows


def usage_summary(run):
    def summarize(attempts):
        models = {}
        for attempt in attempts:
            for row in attempt.get('usage') or []:
                key = (row['provider'], row['model'])
                total = models.setdefault(key, {'provider': key[0], 'model': key[1], 'input_tokens': 0, 'output_tokens': 0, 'cost_usd': Decimal(0)})
                for field in ('input_tokens', 'output_tokens', 'cost_usd'):
                    value = row[field]
                    if value is None or total[field] is None:
                        total[field] = None
                    else:
                        total[field] += Decimal(value) if field == 'cost_usd' else value
        rows = [{**v, 'cost_usd': str(v['cost_usd']) if v['cost_usd'] is not None else None} for v in models.values()]
        missing = any(a.get('usage') is None for a in attempts)
        return {'status': 'partial' if missing and rows else 'unavailable' if missing or not attempts else 'reported' if rows else 'not_applicable', 'models': rows}
    return {**summarize(run['attempts']), 'cases': [
        {'tc_id': tc['id'], **summarize([a for a in run['attempts'] if a['tc_id'] == tc['id']])}
        for tc in run['tests']]}
