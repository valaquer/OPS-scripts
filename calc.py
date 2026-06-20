#!/usr/bin/env python3
"""Safe math CLI for teammates. Expression in, answer out."""

import sys
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

# Use venv's asteval
VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calc-venv")
sys.path.insert(0, os.path.join(VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from asteval import Interpreter


def days(d1, d2):
    """Absolute days between two ISO date strings."""
    a = datetime.strptime(d1, "%Y-%m-%d").date()
    b = datetime.strptime(d2, "%Y-%m-%d").date()
    return abs((b - a).days)


def missing_days(d1, d2):
    """Dates between two ISO date strings, exclusive of endpoints."""
    a = datetime.strptime(d1, "%Y-%m-%d").date()
    b = datetime.strptime(d2, "%Y-%m-%d").date()
    if a > b:
        a, b = b, a
    result = []
    current = a + timedelta(days=1)
    while current < b:
        result.append(current.strftime("%b %d").replace(" 0", " "))
        current += timedelta(days=1)
    if not result:
        return "No missing days"
    return ", ".join(result)


def today():
    """Today's date as ISO string."""
    return date.today().isoformat()


def format_result(result):
    """Format output for humans."""
    if result is None:
        return ""
    if isinstance(result, float):
        if result == int(result):
            return str(int(result))
        return str(round(result, 2))
    if isinstance(result, Decimal):
        return str(result.quantize(Decimal("0.01")))
    return str(result)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 calc.py 'expression'")
        print()
        print("Examples:")
        print("  python3 calc.py '23.50 + 45.99 + 12.30'")
        print('  python3 calc.py \'days("2026-06-15", "2026-06-12")\'')
        print('  python3 calc.py \'missing_days("2026-06-12", "2026-06-15")\'')
        print("  python3 calc.py 'today()'")
        sys.exit(1)

    expr = " ".join(sys.argv[1:])

    # Strip currency labels (EUR, USD) so Felix can write "23.50 EUR + 45.99 EUR"
    expr = re.sub(r'\b(EUR|USD)\b', '', expr).strip()

    aeval = Interpreter(use_numpy=False)

    # Inject date functions
    aeval.symtable["days"] = days
    aeval.symtable["missing_days"] = missing_days
    aeval.symtable["today"] = today

    # Inject stdlib types
    aeval.symtable["date"] = date
    aeval.symtable["datetime"] = datetime
    aeval.symtable["timedelta"] = timedelta
    aeval.symtable["Decimal"] = Decimal

    try:
        result = aeval(expr)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    if aeval.error:
        for err in aeval.error:
            print(f"Error: {err.msg}")
        sys.exit(1)

    print(format_result(result))


if __name__ == "__main__":
    main()
