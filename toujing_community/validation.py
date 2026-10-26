"""Server-side allowlist for the exact public investment card."""
from copy import deepcopy
from datetime import date
from jsonschema import Draft202012Validator


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required, 'additionalProperties': False}


def string(limit):
    return {'type': 'string', 'minLength': 1, 'maxLength': limit}


NUMBER = {'type': 'number'}
METRICS = obj({
    'returnValue': {'type': 'number', 'minimum': -1},
    'maxDrawdown': {'type': 'number', 'minimum': -1, 'maximum': 0},
    'pnl': NUMBER, 'equity': NUMBER, 'netContributions': NUMBER,
    'holdingCount': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991},
    'closedCount': {'type': 'integer', 'minimum': 0, 'maximum': 9007199254740991}}, [])
CARD = obj({
    'schema': {'const': 'toujing-investment-share'}, 'version': {'const': 1},
    'kind': {'enum': ['episode', 'holdings', 'period']},
    'source': {'enum': ['synthetic', 'local_account', 'user_reported']},
    'currency': {'enum': ['CNY', 'USD', 'HKD']},
    **{k: {'type': 'string', 'pattern': r'^\d{4}-\d{2}-\d{2}$'} for k in ['asOf', 'start', 'end']},
    'instrument': string(120), 'status': {'enum': ['open', 'closed']},
    'holdings': {'type': 'array', 'maxItems': 100, 'items': obj({'name': string(120), 'weight': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'marketValue': {'type': 'number', 'minimum': 0}}, ['name'])},
    'metrics': METRICS, 'returnBasis': {'enum': ['episode_cost', 'time_weighted', 'user_reported', 'unavailable']},
    'pnlBasis': {'enum': ['period', 'episode', 'realized', 'user_reported']},
    'definitions': {'type': 'array', 'maxItems': 20, 'items': string(500)},
    'disclosure': obj({k: {'type': 'boolean'} for k in ['names', 'weights', 'performance', 'amounts', 'dates', 'counts']}, ['names', 'weights', 'performance', 'amounts', 'dates'])
}, ['schema', 'version', 'kind', 'source', 'currency', 'holdings', 'metrics', 'returnBasis', 'pnlBasis', 'definitions', 'disclosure'])
NARRATIVE = obj({'title': string(160), 'thesis': string(4000), 'risk': string(1600), 'watch': string(1000)})


def validate(value, schema):
    if not Draft202012Validator(schema).is_valid(value):
        raise ValueError('字段格式或展示范围无效，请重新检查预览。')


def card_for_members(value):
    validate(value, CARD)
    c = deepcopy(value)
    d, m, hs = c['disclosure'], c['metrics'], c['holdings']
    for field in ('asOf', 'start', 'end'):
        if field in c:
            date.fromisoformat(c[field])
    if d['dates'] and 'asOf' not in c or not d['dates'] and any(k in c for k in ('asOf', 'start', 'end')):
        raise ValueError('日期展示范围不一致。')
    for a, b in [('start', 'end'), ('start', 'asOf'), ('end', 'asOf')]:
        if a in c and b in c and c[a] > c[b]:
            raise ValueError('日期区间无效。')
    if (not d['names'] and ('instrument' in c or any(h['name'] != f'持仓 {i+1}' for i, h in enumerate(hs)))
        or not d['weights'] and any('weight' in h for h in hs)
        or not d['amounts'] and (any(k in m for k in ('pnl', 'equity', 'netContributions')) or any('marketValue' in h for h in hs))
        or not d['performance'] and any(k in m for k in ('returnValue', 'maxDrawdown'))
        or d.get('counts') is False and any(k in m for k in ('holdingCount', 'closedCount'))):
        raise ValueError('包含未选择展示的投资数据。')
    if sum(h.get('weight', 0) for h in hs) > 1.000001:
        raise ValueError('持仓比例合计不能超过 100%。')
    # A member client cannot attest broker provenance or a trusted calculation method.
    c['source'] = 'synthetic' if c['source'] == 'synthetic' else 'user_reported'
    c['returnBasis'] = 'user_reported' if 'returnValue' in m else 'unavailable'
    c['pnlBasis'] = 'user_reported'
    c['definitions'] = ['演示数据，不代表真实投资表现。' if c['source'] == 'synthetic' else '由发布者提供，未经券商或第三方核验；仅展示发布者选择的数据。']
    return c


def narrative(value):
    validate(value, NARRATIVE)
    clean = {k: v.strip() for k, v in value.items()}
    import re
    watches = [x.strip() for x in re.split(r'[\n；;]', clean['watch']) if x.strip()]
    if not all(clean.values()) or not watches or len(watches) > 20 or any(len(w) > 240 for w in watches):
        raise ValueError('请填写完整说明，每条观察事项不超过 240 字，最多 20 条。')
    clean['watchpoints'] = watches
    del clean['watch']
    return clean
