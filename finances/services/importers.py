import re
from datetime import datetime
import pandas as pd
import html
from django.db import transaction as db_transaction
from ..models import Transaction
from .classify import clean_val, build_item_library, build_pattern_rules, classify


# ---------------------------------------------------------------------------
# SQUARE
#
# Same logic as the standalone reporter script: revenue-protection pricing,
# fee splitting across multi-item rows, and daily reconciliation so the
# report always ties out exactly to Square's own daily totals. The only
# difference is this writes Transaction rows tied to an ImportBatch instead
# of building a downloadable CSV.
# ---------------------------------------------------------------------------

def import_square(df, batch):
    desc_col = next((c for c in ['Description', 'Item', 'Items'] if c in df.columns), None)
    gross_col = next((c for c in ['Gross Sales', 'Gross'] if c in df.columns), None)
    fee_col = next((c for c in ['Fees', 'Fee'] if c in df.columns), None)
    date_col = next((c for c in ['Date', 'Transaction Date'] if c in df.columns), None)

    if not all([desc_col, gross_col, fee_col, date_col]):
        raise ValueError("Could not detect required columns (Description/Gross/Fees/Date) in this file.")

    library_map = build_item_library()
    pattern_rules = build_pattern_rules()

    all_rows = []  # working dicts before reconciliation

    for _, row in df.iterrows():
        t_gross = clean_val(row[gross_col])
        t_fee = clean_val(row[fee_col])
        raw_desc = str(row[desc_col]).strip()

        whole_info, whole_extra = classify(raw_desc, library_map, pattern_rules)
        if whole_info['min'] != 'Unknown':
            parts = [raw_desc]
        else:
            parts = [p.strip() for p in raw_desc.split(',')]

        line_items = []
        known_price_sum = 0.0

        for part in parts:
            m = re.match(r'^(?:(\d+)\s+x\s+)?(.+)$', part)
            qty = int(m.group(1)) if m.group(1) else 1
            name = m.group(2).strip()

            info, extra = classify(name, library_map, pattern_rules)
            if info['min'] == 'Unknown' and whole_info['min'] != 'Unknown':
                info, extra = whole_info, whole_extra

            if len(parts) == 1 or info['price'] == 'variable':
                price = t_gross / qty if len(parts) == 1 else 0.0
            else:
                price = info['price']

            line_gross = qty * price
            is_v = info['price'] == 'variable' and len(parts) > 1
            line_items.append({
                "item": name, "qty": qty, "gross": line_gross,
                "ministry": info['min'], "is_v": is_v, "extra": extra,
            })
            if not is_v:
                known_price_sum += line_gross

        vars_list = [i for i in line_items if i['is_v']]
        if vars_list:
            rem = t_gross - known_price_sum
            for i, v in enumerate(vars_list):
                v['gross'] = rem if i == len(vars_list) - 1 else round(rem / len(vars_list), 2)
                rem -= v['gross']
        elif abs(known_price_sum - t_gross) > 0.001 and t_gross != 0:
            for i in line_items:
                i['gross'] = (i['gross'] / known_price_sum) * t_gross

        row_f_sum = 0.0
        for i, item in enumerate(line_items):
            if i == len(line_items) - 1:
                item['fee'] = round(t_fee - row_f_sum, 2)
            else:
                ratio = item['gross'] / t_gross if t_gross != 0 else 0
                item['fee'] = round(t_fee * ratio, 2)
                row_f_sum += item['fee']
            item['gross'] = round(item['gross'], 2)
            item['date'] = pd.to_datetime(row[date_col]).date()
            item['external_id'] = str(row.get('Transaction ID', ''))
            all_rows.append(item)

    # Daily reconciliation: force each day's totals to match Square exactly,
    # same as the standalone script (absorbs rounding into the last line of
    # each day).
    by_date = {}
    for r in all_rows:
        by_date.setdefault(r['date'], []).append(r)

    df_dates = pd.to_datetime(df[date_col]).dt.date
    final = []
    for date, rows in by_date.items():
        day_mask = df_dates == date
        target_g = round(df.loc[day_mask, gross_col].apply(clean_val).sum(), 2)
        target_f = round(df.loc[day_mask, fee_col].apply(clean_val).sum(), 2)
        diff_g = round(target_g - sum(r['gross'] for r in rows), 2)
        diff_f = round(target_f - sum(r['fee'] for r in rows), 2)
        if rows:
            rows[-1]['gross'] = round(rows[-1]['gross'] + diff_g, 2)
            rows[-1]['fee'] = round(rows[-1]['fee'] + diff_f, 2)
        final.extend(rows)

    objs = [
        Transaction(
            batch=batch, source='square', date=r['date'], ministry=r['ministry'],
            item=r['item'], qty=r['qty'], gross=r['gross'], fees=r['fee'],
            net=round(r['gross'] + r['fee'], 2), external_id=r['external_id'],
            extra=r['extra'],
        )
        for r in final
    ]
    Transaction.objects.bulk_create(objs)
    return len(objs)


# ---------------------------------------------------------------------------
# STRIPE
#
# Much simpler: Stripe's export already tags each charge with the event/
# reason (payment_metadata[Event Name]) which IS the ministry — no
# classification needed, just column mapping.
# ---------------------------------------------------------------------------

def clean_text(raw_text):
    if pd.isna(raw_text) or not isinstance(raw_text, str):
        return ""
    return html.unescape(raw_text).replace('â€™', "'").strip()

def import_stripe(df, batch):
    ministry_col = next((c for c in df.columns if 'Event Name' in c), None) or 'reporting_category'
    gross_col = 'gross' if 'gross' in df.columns else 'Amount'
    fee_col = 'fee' if 'fee' in df.columns else 'Fee'
    net_col = 'net' if 'net' in df.columns else 'Net'
    date_col = 'created' if 'created' in df.columns else 'Created date (UTC)'
    id_col = 'source_id' if 'source_id' in df.columns else 'id'
    ref_col = 'description' if 'description' in df.columns else None

    objs = []
    for _, row in df.iterrows():
        gross = clean_val(row.get(gross_col))
        fee = clean_val(row.get(fee_col))
        net = clean_val(row.get(net_col)) if net_col in df.columns else round(gross - fee, 2)
        
        # Clean text to remove HTML entities and bad quotes
        ministry = clean_text(str(row.get(ministry_col) or 'Unknown'))
        item_desc = clean_text(str(row.get(ref_col) or ''))
        
        # Combine Event Name and Description if both exist
        event_name = clean_text(str(row.get('payment_metadata[Event Name]') or ''))
        if event_name and item_desc and event_name != item_desc:
            item_desc = f"{event_name} ({item_desc})"
        elif event_name:
            item_desc = event_name

        date_val = pd.to_datetime(row.get(date_col), errors='coerce')
        if pd.isna(date_val):
            continue
            
        external_id = str(row.get(id_col, '')).strip()

        objs.append(Transaction(
            batch=batch, source='stripe', date=date_val.date(), ministry=ministry,
            item=item_desc, qty=1, gross=gross, fees=fee, net=net, external_id=external_id
        ))
    Transaction.objects.bulk_create(objs)
    batch.row_count = len(objs)
    batch.save(update_fields=['row_count'])

def import_stripe_ytd(df, batch):
    """Links the YTD customer names to existing Stripe transactions."""
    id_col = 'id'
    name_col = 'Card Name'
    if id_col not in df.columns or name_col not in df.columns:
        return
    
    card_names = dict(zip(df[id_col], df[name_col].fillna('')))
    
    updated_count = 0
    stripe_txns = Transaction.objects.filter(source='stripe')
    
    with db_transaction.atomic():
        for txn in stripe_txns:
            if txn.external_id in card_names:
                name = clean_text(card_names[txn.external_id])
                if name:
                    txn.extra['customer_name'] = name
                    txn.save(update_fields=['extra'])
                    updated_count += 1
                    
    batch.row_count = updated_count
    batch.save(update_fields=['row_count'])

# (For import_square, just wrap `row[desc_col]` in `clean_text(str(row[desc_col]))` to fix its encoding too).