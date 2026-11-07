"""Export a small presentation archive from Toujing's existing Decimal ledger.

Run with the product environment, passing --product-root. No database, model,
or account is opened. --check verifies the committed archive without writing.
This adapter supports the frozen teaching account only, not arbitrary imports.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
import json
from pathlib import Path
import sys

FRONTEND = Path(__file__).resolve().parents[1]


def build(product_root: Path) -> dict:
    sys.path.insert(0, str(product_root))
    from src.ledger.engine import project
    from src.ledger.contracts import dividend_tax_view
    from src.research_workbench.market import ArchiveMarket
    from src.research_workbench.personal_review import demo_ledger_inputs
    from src.research_workbench.contracts import digest

    demo_bytes = (FRONTEND / 'public/demo-data.json').read_bytes()
    demo = json.loads(demo_bytes)
    market = ArchiveMarket()
    portfolio = market.portfolio
    fingerprint = digest({'bars': portfolio['bars'], 'trades': portfolio['executions'], 'events': portfolio['events']})
    if fingerprint != demo['source_fingerprint']:
        raise ValueError('The demo and ledger inputs differ; do not publish stale episode results.')
    cutoff = portfolio['period']['end']
    ledger = project(*demo_ledger_inputs(market, cutoff), as_of=cutoff, include_record_index=True)
    if ledger['status'] != 'available' or ledger['errors']:
        raise ValueError('The source ledger is not fully available.')
    actual = next(path for path in demo['paths'] if path['id'] == 'actual')
    if any(ledger[key] != actual['summary'][key] for key in ('equity', 'cash', 'period_pnl', 'net_income')):
        raise ValueError('The episode projection does not reconcile with the displayed account.')

    assets = {a['symbol']: a for a in portfolio['assets']}
    fills = {row['execution_id']: row for row in actual['fills']}
    source_fills = {row['execution_id']: row for row in portfolio['executions']}
    binding_fields = ('execution_id', 'date', 'ticker', 'side', 'quantity', 'price', 'fee')
    binding = [{key: row[key] for key in binding_fields} for row in actual['fills']]
    for row in binding:
        if row != {key: source_fills[row['execution_id']][key] for key in binding_fields}:
            raise ValueError('The visible executions differ from the exact ledger inputs.')

    # Grouping, fees, average cost and share changes all come from project().
    # The adapter only joins dividend receipts and prepares display fields.
    counts = Counter(ep['symbol'] for ep in ledger['episodes'])
    rounds = Counter()
    episodes = []
    ownership = {}
    cash_income = Decimal(0)
    event_ids = []
    for ep in ledger['episodes']:
        rounds[ep['symbol']] += 1
        last = ep['path'][-1]
        trades = []
        for ref in ep['source_refs']:
            if not ref.startswith('execution:'):
                continue
            execution_id = ref.removeprefix('execution:')
            if execution_id in ownership:
                raise ValueError('An execution belongs to more than one episode.')
            ownership[execution_id] = ep['episode_id']
            fill = fills[execution_id]
            state = ledger['record_index']['execution_states'][ref]
            before, after = state['before']['quantity'], state['after']['quantity']
            label = ('建仓' if Decimal(before) == 0 else '加仓') if fill['side'] == 'BUY' else ('清仓' if Decimal(after) == 0 else '减仓')
            trades.append({'id': execution_id, 'kind': 'trade', 'date': fill['date'], 'label': label,
                           'execution_id': execution_id, 'side': fill['side'], 'quantity': fill['quantity'],
                           'price': fill['price'], 'fee': fill['fee'], 'position_before': before,
                           'position_after': after, 'cash_before': state['before']['cash'],
                           'cash_after': state['after']['cash']})
        receipts = []
        dividends = Decimal(0)
        for event in portfolio['events']:
            if event.get('instrument', {}).get('instrument_id') != ep['instrument_id']:
                continue
            if event['event_type'] == 'cash_dividend':
                ex_day = event['ex_date']
                # The frozen demo's entitlements are before trades on ex-day.
                # Same-day new/reopened positions need a richer entitlement link.
                if not ep['opened_at'] < ex_day <= (ep['closed_at'] or cutoff):
                    continue
                tax = dividend_tax_view(event)
                if tax['tax_status'] == 'unknown' or event['effective_date'] > cutoff:
                    raise ValueError('Unsettled/unknown-tax dividend requires explicit receivable handling.')
                amount = Decimal(event['amount']) - Decimal(tax['tax'])
                dividends += amount
                receipts.append({'id': event['event_id'], 'kind': 'dividend', 'label': '现金分红',
                    'date': event['effective_date'], 'ex_date': ex_day, 'amount': str(amount),
                    'source_ref': event['source_ref'], 'note': event['note']})
                event_ids.append(event['event_id'])
            elif event['event_id'] in ep['source_refs']:
                if event['event_type'] != 'split':
                    raise ValueError('This presentation adapter requires a new contract for this company action.')
                receipts.append({'id': event['event_id'], 'kind': 'split', 'label': '送转股',
                    'date': event['effective_date'], 'ratio': event['ratio'],
                    'source_ref': event['source_ref'], 'note': event['note']})
                event_ids.append(event['event_id'])
        realized = Decimal(ep['realized_pnl'])
        unrealized = Decimal(last['market_value']) - Decimal(last['cost_basis'])
        result = realized + unrealized + dividends
        money = lambda value: format(value.quantize(Decimal('.01'), rounding=ROUND_HALF_EVEN), 'f')
        events = sorted([*trades, *receipts], key=lambda item: (item['date'], 0 if item['kind'] == 'split' else 1 if item['kind'] == 'trade' else 2, item['id']))
        episodes.append({'id': ep['episode_id'], 'ticker': assets[ep['symbol']]['ticker'],
            'name': assets[ep['symbol']]['name'], 'symbol': ep['symbol'], 'round': rounds[ep['symbol']],
            'rounds': counts[ep['symbol']], 'status': ep['status'], 'opened_at': ep['opened_at'],
            'closed_at': ep['closed_at'], 'as_of': cutoff, 'currency': 'CNY',
            'quantity': last['quantity'], 'market_value': last['market_value'],
            'cost_basis': last['cost_basis'], 'invested_cost': ep['invested_cost'],
            'realized_pnl': ep['realized_pnl'], 'unrealized_pnl': str(unrealized),
            'dividend_income': str(dividends), 'pnl': str(result),
            'display': {'pnl': money(result), 'realized_pnl': money(realized),
                        'unrealized_pnl': money(unrealized), 'dividend_income': money(dividends)},
            'trade_ids': [t['execution_id'] for t in trades], 'events': events})
        cash_income += dividends
    if set(ownership) != set(fills):
        raise ValueError('Every displayed execution must belong to exactly one episode.')
    company_events = {e['event_id'] for e in portfolio['events'] if e.get('instrument')}
    if set(event_ids) != company_events or len(event_ids) != len(set(event_ids)):
        raise ValueError('Every company action must be assigned once, including entitlements at boundaries.')
    if cash_income != Decimal(ledger['net_income']):
        raise ValueError('Episode dividends do not reconcile to account income.')
    total = sum((Decimal(e['pnl']) for e in episodes), Decimal(0))
    if abs(total - Decimal(ledger['period_pnl'])) > Decimal('1e-65'):
        raise ValueError('Episode results do not reconcile with account P&L.')
    return {'schema_version': 'investment_episodes.v1', 'source_fingerprint': fingerprint,
        'demo_data_sha256': sha256(demo_bytes).hexdigest(), 'as_of': cutoff,
        'data_tier': 'real_archived_prices_authored_demo_trades', 'execution_binding': binding,
        'method': {'engine': 'src/ledger/engine.py:project',
            'adapter': 'scripts/build-investment-episodes.py',
            'formula': '本轮盈亏 = 已实现交易盈亏 + 期末浮动盈亏 + 本轮分红',
            'cost_basis': '含成交费用的移动平均成本；送转沿用原账本处理。',
            'dividend_basis': '演示分红沿用原账户的税前、除息日到账假设。',
            'display_rounding': '保留原始 Decimal 结果，展示四舍六入五成双至人民币分。',
            'source_files': {name: sha256((product_root / name).read_bytes()).hexdigest() for name in (
                'src/ledger/engine.py', 'src/ledger/contracts.py', 'src/research_workbench/personal_review.py')}},
        'summary': {'episode_count': len(episodes), 'trade_count': len(fills),
            'open_count': sum(e['status'] == 'open' for e in episodes),
            'closed_count': sum(e['status'] == 'closed' for e in episodes),
            'pnl': ledger['period_pnl'], 'dividend_income': ledger['net_income']},
        'episodes': episodes}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-root', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    with localcontext() as context:
        context.prec = 80
        archive = build(args.product_root.resolve())
    content = json.dumps(archive, ensure_ascii=False, indent=2) + '\n'
    target = FRONTEND / 'public/investment-episodes.json'
    if args.check:
        if target.read_text() != content:
            raise SystemExit('The episode archive is not reproducible from the current source.')
        print('Exact ledger / 13 episodes / 54 executions / company actions / account P&L: verified.')
    else:
        target.write_text(content)
        print(f'Wrote {target.name}: {len(content.encode())} bytes; {archive["summary"]}')
