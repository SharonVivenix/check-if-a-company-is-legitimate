#!/usr/bin/env python3
"""legit_check.py: score whether a company is legitimate by what its evidence costs to fake.

Standard library only, Python 3.8+.

    python3 legit_check.py examples/northgate_supplies.json
    python3 legit_check.py examples/quickship_trading.json --json
    python3 legit_check.py --domain example.org            # live web layer only
    python3 legit_check.py profile.json --live             # profile plus live probes

Every check carries a fake cost. A padlock costs nothing to fake, a regulator
register entry costs a licence application. PROCEED is only reachable when at
least one expensive check passes, so a polished website alone never clears.

Exit codes:
    0 proceed, 1 verify further, 2 stop, 3 input error
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

# Points a passing check earns, by how hard the evidence is to fabricate.
FAKE_COST = {"free": 0.5, "low": 1.5, "medium": 4.0, "high": 7.0}

FREEMAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me",
            "protonmail.com", "icloud.com", "aol.com", "mail.ru", "gmx.com", "yandex.ru"}

# Payment rails that are hard or impossible to reverse once sent.
IRREVERSIBLE = {"wire", "crypto", "gift_card", "money_order", "cash"}
REVERSIBLE = {"card", "paypal", "ach_debit", "invoice_net_terms", "escrow"}

USER_AGENT = "legit-check/1.0 (+https://github.com/SharonVivenix/check-if-a-company-is-legitimate)"
TIMEOUT = 15


class ProfileError(ValueError):
    pass


class Finding:
    __slots__ = ("check", "layer", "cost", "status", "detail", "hard_stop")

    def __init__(self, check, layer, cost, status, detail, hard_stop=False):
        self.check, self.layer, self.cost = check, layer, cost
        self.status, self.detail, self.hard_stop = status, detail, hard_stop

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def _years_since(iso_date, today):
    if not iso_date:
        return None
    try:
        d = dt.date.fromisoformat(str(iso_date)[:10])
    except ValueError:
        raise ProfileError(f"bad date: {iso_date!r}, expected YYYY-MM-DD")
    return (today - d).days / 365.25


# ---------------------------------------------------------------- checks

def check_registry(p, today):
    r = p.get("registry") or {}
    out = []
    found = r.get("found")
    if found is None:
        out.append(Finding("registry_record", "identity", "high", "unknown",
                           "no registry lookup recorded"))
        return out
    if not found:
        out.append(Finding("registry_record", "identity", "high", "fail",
                           f"no record for {r.get('company_number', '?')} in {r.get('jurisdiction', '?')}",
                           hard_stop=True))
        return out
    status = (r.get("status") or "").lower()
    if status and status != "active":
        out.append(Finding("registry_record", "identity", "high", "fail",
                           f"registry status is {status}", hard_stop=True))
        return out
    if r.get("name_matches") is False:
        out.append(Finding("registry_record", "identity", "high", "fail",
                           "registered name differs from the trading name you were given"))
    else:
        out.append(Finding("registry_record", "identity", "high", "pass",
                           f"active record {r.get('company_number', '')} in {r.get('jurisdiction', '')}".strip()))

    age = _years_since(r.get("incorporated"), today)
    problems = []
    if r.get("address_matches") is False:
        problems.append("registered address differs from the address on the contract")
    if age is not None and age < 0.5:
        problems.append(f"incorporated {age * 12:.0f} months ago")
    if r.get("recent_name_changes", 0) >= 2:
        problems.append(f"{r['recent_name_changes']} name changes in 24 months")
    if problems:
        out.append(Finding("registry_consistency", "identity", "medium", "warn", ", ".join(problems)))
    elif age is not None:
        out.append(Finding("registry_consistency", "identity", "medium", "pass",
                           f"incorporated {age:.1f} years ago, details consistent"))
    return out


def check_licence(p, today):
    lic = p.get("licence")
    if not lic or not lic.get("required"):
        return []
    reg = lic.get("register", "regulator register")
    if lic.get("found") is None:
        return [Finding("licence", "identity", "high", "unknown", f"{reg} not searched yet")]
    if not lic["found"]:
        return [Finding("licence", "identity", "high", "fail",
                        f"regulated activity but no entry on {reg}", hard_stop=True)]
    return [Finding("licence", "identity", "high", "pass",
                    f"listed on {reg} as {lic.get('reference', 'authorised')}")]


def check_screening(p, today):
    s = p.get("screening")
    if not s:
        return [Finding("screening", "identity", "medium", "unknown",
                        "sanctions, PEP and adverse media screening not run")]
    if s.get("sanctions_hit"):
        return [Finding("screening", "identity", "medium", "fail",
                        "sanctions match on the company or a related person", hard_stop=True)]
    hits = [k for k in ("pep", "adverse_media") if s.get(k)]
    if hits:
        return [Finding("screening", "identity", "medium", "warn", "hit: " + ", ".join(hits))]
    return [Finding("screening", "identity", "medium", "pass", "no sanctions, PEP or adverse media hits")]


def check_website(p, today):
    w = p.get("website") or {}
    out = []
    age = _years_since(w.get("domain_created"), today)
    if age is None:
        out.append(Finding("domain_age", "footprint", "medium", "unknown", "domain creation date unknown"))
    elif age >= 3:
        out.append(Finding("domain_age", "footprint", "medium", "pass", f"domain registered {age:.1f} years ago"))
    else:
        out.append(Finding("domain_age", "footprint", "medium", "warn", f"domain registered {age:.1f} years ago"))

    if "https" in w:
        out.append(Finding("https", "footprint", "free", "pass" if w["https"] else "warn",
                           "valid certificate" if w["https"] else "no valid TLS certificate"))

    pages = [k for k in ("privacy_policy", "terms") if w.get(k)]
    if "privacy_policy" in w or "terms" in w:
        missing = [k for k in ("privacy_policy", "terms") if k not in pages]
        out.append(Finding("policy_pages", "footprint", "low", "warn" if missing else "pass",
                           "missing " + ", ".join(missing) if missing else "privacy policy and terms present"))

    if "company_number_on_site" in w:
        ok = w["company_number_on_site"]
        out.append(Finding("company_number_on_site", "footprint", "low", "pass" if ok else "warn",
                           "registration number printed on site" if ok
                           else "registration number not found on site or policy pages"))
    return out


def check_contact(p, today):
    out = []
    email = p.get("contact_email") or ""
    if email:
        domain = email.rsplit("@", 1)[-1].lower()
        if domain in FREEMAIL:
            out.append(Finding("email_domain", "reachability", "low", "warn", f"business contact on {domain}"))
        elif p.get("domain") and not domain.endswith(p["domain"].lower()):
            out.append(Finding("email_domain", "reachability", "low", "warn",
                               f"email domain {domain} differs from website {p['domain']}"))
        else:
            out.append(Finding("email_domain", "reachability", "low", "pass", f"email on {domain}"))

    if "phone_answered" in p:
        ok = p["phone_answered"]
        out.append(Finding("phone", "reachability", "low", "pass" if ok else "warn",
                           "listed number answered by the company" if ok else "listed number not answered"))

    # A missing key means not assessed. An explicit null means the company gave no address.
    a = p.get("address", {})
    if a is None:
        out.append(Finding("address", "reachability", "medium", "fail", "no physical address given"))
    elif a:
        kind = a.get("type", "unknown")
        if kind == "office" and a.get("verified_visually"):
            out.append(Finding("address", "reachability", "medium", "pass",
                               "office confirmed by street imagery, visit or video walkthrough"))
        elif kind in ("virtual", "mailbox", "registered_agent"):
            out.append(Finding("address", "reachability", "medium", "warn",
                               f"{kind} address, ask where the team actually works"))
        else:
            out.append(Finding("address", "reachability", "medium", "unknown",
                               f"{kind} address, not confirmed visually"))
    return out


def check_reputation(p, today):
    out = []
    rv = p.get("reviews")
    if rv:
        problems = []
        count = rv.get("count", 0)
        if count < 10:
            problems.append(f"only {count} reviews")
        if count and rv.get("five_star_share", 0) >= 0.95:
            problems.append(f"{rv['five_star_share']:.0%} five star, real distributions have a tail")
        if count and rv.get("max_same_day", 0) >= max(5, 0.2 * count):
            problems.append(f"{rv['max_same_day']} reviews posted on a single day")
        if rv.get("scam_lawsuit_hits", 0):
            problems.append(f"{rv['scam_lawsuit_hits']} results for name plus scam or lawsuit")
        out.append(Finding("reviews", "reputation", "medium", "warn" if problems else "pass",
                           ", ".join(problems) if problems else f"{count} reviews, normal spread"))

    ref = p.get("references")
    if ref and ref.get("requested"):
        confirmed = ref.get("confirmed", 0)
        if ref.get("provided", 0) == 0:
            out.append(Finding("references", "reputation", "high", "fail", "references requested, none provided"))
        elif confirmed >= 2:
            out.append(Finding("references", "reputation", "high", "pass",
                               f"{confirmed} references confirmed scope, timeline and satisfaction by phone"))
        else:
            out.append(Finding("references", "reputation", "high", "warn",
                               f"{confirmed} of {ref['provided']} references confirmed"))
    return out


def check_payment(p, today):
    methods = {m.lower() for m in p.get("payment_methods", [])}
    out = []
    if methods:
        if methods <= IRREVERSIBLE:
            out.append(Finding("payment_rails", "payment", "medium", "fail",
                               "only irreversible rails accepted: " + ", ".join(sorted(methods))))
        elif methods & REVERSIBLE:
            out.append(Finding("payment_rails", "payment", "medium", "pass",
                               "reversible rail available: " + ", ".join(sorted(methods & REVERSIBLE))))
        else:
            out.append(Finding("payment_rails", "payment", "medium", "unknown",
                               "unrecognised methods: " + ", ".join(sorted(methods))))
    if p.get("pressure_language"):
        out.append(Finding("pressure", "payment", "low", "warn",
                           "urgency wording such as act now or limited time in the offer"))
    return out


CHECKS = [check_registry, check_licence, check_screening, check_website,
          check_contact, check_reputation, check_payment]


# ---------------------------------------------------------------- verdict

def evaluate(profile, today=None):
    today = today or dt.date.today()
    findings = [f for chk in CHECKS for f in chk(profile, today)]

    possible = sum(FAKE_COST[f.cost] for f in findings if f.status != "unknown")
    earned = sum(FAKE_COST[f.cost] for f in findings if f.status == "pass")
    score = earned / possible if possible else 0.0
    expensive_pass = any(f.status == "pass" and f.cost == "high" for f in findings)
    expensive_doubt = any(f.status in ("warn", "fail") and f.cost == "high" for f in findings)

    if any(f.hard_stop for f in findings):
        verdict = "stop"
    elif any(f.status == "fail" for f in findings):
        verdict = "verify"
    elif score >= 0.75 and expensive_pass and not expensive_doubt:
        verdict = "proceed"
    else:
        verdict = "verify"

    return {
        "company": profile.get("name", "?"),
        "verdict": verdict,
        "score": round(score, 3),
        "expensive_evidence": expensive_pass,
        "findings": [f.as_dict() for f in findings],
    }


EXIT = {"proceed": 0, "verify": 1, "stop": 2}


# ---------------------------------------------------------------- live probes

def _get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.geturl(), resp.read(2_000_000).decode("utf-8", "replace")


def rdap_created(domain):
    """Registration date from RDAP, the structured successor to WHOIS."""
    try:
        _, _, body = _get(f"https://rdap.org/domain/{domain}", {"Accept": "application/rdap+json"})
    except (urllib.error.URLError, socket.timeout, ValueError):
        return None
    for ev in json.loads(body).get("events", []):
        if ev.get("eventAction") == "registration":
            return ev.get("eventDate", "")[:10]
    return None


def tls_ok(domain):
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((domain, 443), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as tls:
                return bool(tls.getpeercert())
    except (ssl.SSLError, OSError):
        return False


LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

# Single page apps ship their footer inside a JSON blob, so plain href parsing
# finds nothing. These paths are tried after any links found in the HTML.
POLICY_PATHS = {
    "privacy_policy": (r"privacy", ["privacy-policy", "privacy", "legal/privacy"]),
    "terms": (r"terms|conditions", ["terms-of-service", "terms", "terms-and-conditions", "legal/terms"]),
}


def probe_site(domain, company_number=None):
    out = {"https": tls_ok(domain)}
    try:
        _, final, html = _get(f"https://{domain}/")
    except (urllib.error.URLError, socket.timeout, ValueError):
        return out
    links = LINK_RE.findall(html.replace("\\", ""))
    texts = [html]
    for key, (pat, fallbacks) in POLICY_PATHS.items():
        candidates = [l for l in links if re.search(pat, l, re.I)][:2] + fallbacks
        out[key] = False
        for cand in candidates:
            try:
                status, _, body = _get(urllib.parse.urljoin(final, cand))
            except (urllib.error.URLError, socket.timeout, ValueError):
                continue
            # A catch all route returns 200 for anything, so the page must mention its subject.
            if status == 200 and re.search(pat, body, re.I):
                out[key] = True
                texts.append(body)
                break
    if company_number:
        needle = re.sub(r"\s", "", company_number).lower()
        out["company_number_on_site"] = any(needle in re.sub(r"\s", "", t).lower() for t in texts)
    return out


def companies_house(number, api_key):
    """UK registry lookup. Needs a free key from developer.company-information.service.gov.uk."""
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    try:
        _, _, body = _get(f"https://api.company-information.service.gov.uk/company/{number}",
                          {"Authorization": f"Basic {token}"})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"found": False}
        raise
    data = json.loads(body)
    return {"found": True, "status": data.get("company_status"),
            "incorporated": data.get("date_of_creation"), "registered_name": data.get("company_name"),
            "registered_address": data.get("registered_office_address")}


def enrich_live(profile):
    domain = profile.get("domain")
    if domain:
        w = profile.setdefault("website", {})
        number = (profile.get("registry") or {}).get("company_number")
        w.update(probe_site(domain, number))
        w["domain_created"] = rdap_created(domain) or w.get("domain_created")

    r = profile.get("registry") or {}
    key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if key and r.get("jurisdiction", "").upper() in ("GB", "UK") and r.get("company_number"):
        ch = companies_house(r["company_number"], key)
        r.update({k: v for k, v in ch.items() if k in ("found", "status", "incorporated")})
        if ch.get("registered_name") and profile.get("name"):
            r["name_matches"] = ch["registered_name"].lower().strip() == profile["name"].lower().strip()
        profile["registry"] = r
    return profile


# ---------------------------------------------------------------- output

MARK = {"pass": "+", "warn": "?", "fail": "x", "unknown": "."}


def render(result):
    lines = [f"{result['company']}  verdict: {result['verdict'].upper()}  "
             f"score: {result['score']:.2f}  expensive evidence: {'yes' if result['expensive_evidence'] else 'no'}",
             ""]
    for f in result["findings"]:
        stop = "  STOP" if f["hard_stop"] else ""
        lines.append(f"  [{MARK[f['status']]}] {f['check']:<24} {f['cost']:<7} {f['detail']}{stop}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check if a company is legitimate, weighted by cost to fake.")
    ap.add_argument("profile", nargs="?", help="company profile JSON")
    ap.add_argument("--domain", help="run only the live web layer against this domain")
    ap.add_argument("--live", action="store_true", help="add RDAP, TLS, site and registry probes")
    ap.add_argument("--json", action="store_true", help="machine readable output")
    ap.add_argument("--today", help="override today's date, YYYY-MM-DD")
    args = ap.parse_args(argv)

    try:
        if args.domain:
            profile = enrich_live({"name": args.domain, "domain": args.domain})
        elif args.profile:
            with open(args.profile, encoding="utf-8") as fh:
                profile = json.load(fh)
            if args.live:
                profile = enrich_live(profile)
        else:
            ap.error("give a profile file or --domain")
        today = dt.date.fromisoformat(args.today) if args.today else None
        result = evaluate(profile, today)
    except (OSError, json.JSONDecodeError, ProfileError) as e:
        print(f"input error: {e}", file=sys.stderr)
        return 3

    print(json.dumps(result, indent=2) if args.json else render(result))
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
