"""Conservative draft checks. Reject conflicting figures; never silently edit them."""
import re
from decimal import Decimal

MONEY = re.compile(r'(?:\$|USD)\s*(\d[\d,]*(?:\.\d{1,2})?)', re.I)
TOTAL = re.compile(r'\b(total|requested|requesting|request of|request for)\b', re.I)


def draft_issues(text, context, task):
    if task not in {'proposal', 'budget', 'loi', 'renewal'}:
        return []
    expected = (context.get('application') or {}).get('amount_requested')
    expected = Decimal(str(expected)) if expected is not None else None
    items, totals, requests, issues = [], [], [], []
    for line in text.splitlines():
        amounts = [Decimal(m.replace(',', '')) for m in MONEY.findall(line)]
        if not amounts:
            continue
        if TOTAL.search(line):
            if re.search(r'\brequest(?:ed|ing)?\b', line, re.I):
                requests.append(amounts[-1])
            if re.search(r'\btotal\b',line,re.I) or not re.search(r'\brequest(?:ed|ing)?\b',line,re.I):
                totals.append(amounts[-1])
        elif re.match(r'^\s*(?:[-*•]|\d+[.)]|\|)', line) and not re.search(r'\b(unit cost|per unit|subtotal)\b', line, re.I):
            items.append(amounts[-1])
    if items and totals and any(sum(items) != total for total in totals):
        issues.append(f'Budget line items total ${sum(items):,.2f}, which conflicts with the stated total. Reconcile the figures.')
    if expected is not None and any(amount != expected for amount in requests + totals):
        issues.append(f'The draft funding total does not match the saved requested amount ${expected:,.2f}. Explain cost sharing separately or revise the request explicitly.')
    if expected is not None and items and not totals and not requests and sum(items) != expected:
        issues.append(f'Budget line items do not match the saved requested amount ${expected:,.2f}.')
    # A percentage is not evidence merely because an AI repeats it from its own draft.
    sources = context.get('knowledge_documents') or []
    for line in text.splitlines():
        percentages = re.findall(r'\b\d+(?:\.\d+)?\s*%', line)
        if not percentages or '[information needed]' in line.lower():
            continue
        if re.search(r'\b(target|goal|proposed|projection|aim|hypothetical)\b', line, re.I):
            continue
        if not re.search(r'\b(increase|improv|reduc|outcome|impact|achiev|success|participant|graduate|student)', line, re.I):
            continue
        supported = all(any(p in str(d.get('excerpt') or d.get('summary') or '') and d.get('title') and d['title'].casefold() in line.casefold() for d in sources) for p in percentages)
        if not supported:
            issues.append('An outcome percentage lacks a matching cited evidence source. Use [information needed] or a clearly labelled proposed target.')
            break
    return issues


def validate_draft(text, context, task):
    issues = draft_issues(text, context, task)
    if issues:
        from services.ai_service import AIUnavailable
        raise AIUnavailable('AI draft withheld. ' + ' '.join(issues) + ' Your saved application has not changed.')
    return text
