import re
from ..models import ItemPrice, PatternRule


def clean_val(v):
    if v is None:
        return 0.0
    s = re.sub(r'[^\d.-]', '', str(v))
    try:
        return float(s)
    except ValueError:
        return 0.0


def build_item_library():
    """Mirrors the old parse_item_library(), but reads from ItemPrice rows
    instead of key.csv."""
    mapping = {}
    for ip in ItemPrice.objects.all():
        price = float(ip.price) if ip.price is not None else 'variable'
        info = {"price": price, "min": ip.ministry}
        base = ip.item_name.strip()
        var = ip.variation_name.strip() or 'Regular'
        stripped = re.sub(r'^\d+x\s*', '', base).strip()
        for n in [base, f"{base} ({var})", stripped, f"{stripped} ({var})"]:
            if n:
                mapping[n] = info
    return mapping


def build_pattern_rules():
    """Compiled, priority-ordered PatternRule list."""
    rules = []
    for r in PatternRule.objects.filter(active=True).order_by('priority'):
        try:
            compiled = re.compile(r.pattern)
        except re.error:
            continue  # bad regex saved via admin shouldn't crash imports
        rules.append((compiled, r.fixed_ministry))
    return rules


def classify(name, library_map, pattern_rules):
    """
    Try pattern rules first (subscriptions, merch, anything not in the
    Item Library), then fall back to the exact key lookup (genuine POS
    Item Library sales). Returns (info, extra) where info = {"price", "min"}
    and extra is a dict of any named regex groups for the JSON 'extra' field.
    """
    for compiled, fixed_ministry in pattern_rules:
        m = compiled.match(name)
        if not m:
            continue
        groups = m.groupdict()
        ministry = fixed_ministry or groups.get('ministry') or 'Unknown'
        extra = {k: v for k, v in groups.items() if k != 'ministry' and v is not None}
        return {"price": "variable", "min": ministry}, extra

    return library_map.get(name, {"price": "variable", "min": "Unknown"}), {}
