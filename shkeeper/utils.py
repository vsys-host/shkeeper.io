from decimal import Decimal

def remove_exponent(d: Decimal) -> Decimal:
    return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()

def format_decimal(d: Decimal, precision: int = 8) -> str:
    # f = str(round(d, precision).normalize())
    # return f.rstrip('0').rstrip('.') if '.' in f else f
    return f'{remove_exponent(d):,}'
