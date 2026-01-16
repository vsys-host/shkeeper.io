from decimal import Decimal


def remove_exponent(d: Decimal) -> str:
    # return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()
    try:
        return ("%.10f" % d).rstrip("0").rstrip(".")
    except TypeError:
        return "0"


def format_decimal(d: Decimal, precision: int = 8, st: bool = False) -> str:
    # separate thousands
    if st:
        return f"{remove_exponent(d):,}"
    else:
        return str(remove_exponent(d))

