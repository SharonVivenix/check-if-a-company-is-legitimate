# Check if a Company is Legitimate

<p align="center">
  <a href="https://www.idenfy.com/">
  </a>
</p>

Most advice on how to [check if a company is legitimate](https://www.idenfy.com/business-verification-services/) is a checklist: padlock in the browser, privacy policy, reviews, a phone number. Every item on that list is real, and almost every item is cheap to fake. A TLS certificate costs nothing. A privacy policy is a copy and paste. Two hundred five star reviews cost a few hundred dollars. A checklist that weights all of these the same will happily approve a well built front.

This repo scores evidence by what it would cost a fraudster to produce. [legit_check.py](legit_check.py) is a standard library only Python script that reads a company profile, runs fifteen checks across five layers, and refuses to return PROCEED unless at least one expensive piece of evidence has passed. It can also probe a live domain for the web layer (RDAP registration date, TLS, policy pages, registration number on site) and pull a UK record from the Companies House API when you give it a key.

```text
profile.json  (or --domain example.org)
     |
     v
 identity       footprint        reachability     reputation      payment
 registry       domain age       email domain     reviews         rails
 licence        https            phone            references      pressure
 screening      policy pages     address
                company number
     |
     v
 score = points earned / points assessed, weighted by fake cost
 verdict: PROCEED (exit 0) | VERIFY (exit 1) | STOP (exit 2)
```

## The cost to fake ladder

This table is the core of the repo. Each check gets points by how hard its evidence is to fabricate, not by how reassuring it looks.

| Fake cost | Points | Checks | What a fraudster needs |
| --- | --- | --- | --- |
| free | 0.5 | `https` | Nothing. Free certificates are issued automatically to any domain |
| low | 1.5 | `policy_pages`, `company_number_on_site`, `email_domain`, `phone`, `pressure` | A template, a cheap domain, a virtual number |
| medium | 4 | `domain_age`, `registry_consistency`, `screening`, `address`, `reviews`, `payment_rails` | Time, a bought aged domain, a real office, a review farm that survives scrutiny |
| high | 7 | `registry_record`, `licence`, `references` | A filed legal entity in good standing, a regulator authorisation, real customers who pick up the phone |

Two rules sit on top of the arithmetic:

1. **No PROCEED without expensive evidence.** A profile that passes every free, low and medium check still lands on VERIFY. The test suite includes exactly that case (`test_cheap_evidence_alone_never_proceeds`), a company with a domain registered in 2015, valid TLS and every policy page, but no registry lookup and no references.
2. **Some failures stop the case outright.** A dissolved or missing registry record, a regulated activity with no licence on the relevant register, or a sanctions match each return STOP regardless of score.

Unknown checks are excluded from the denominator instead of counting as failures. A check you have not run yet is a gap, not a red flag, and the report shows it with a `.` so the gap stays visible.

## How to verify a company is real, check by check

The fifteen checks map onto the steps in iDenfy's ten step guide, regrouped by what each one actually proves.

| Check | Layer | Passes when | Does not prove |
| --- | --- | --- | --- |
| `registry_record` | identity | Active record, registered name matches the name you were given | That the people you talk to work there |
| `registry_consistency` | identity | Registered address matches the contract, incorporated over 6 months ago, fewer than 2 name changes in 24 months | That the address is staffed |
| `licence` | identity | Entry found on the regulator register for the activity (only runs when `required` is true) | That the licence covers this exact product |
| `screening` | identity | No sanctions, PEP or adverse media hit on the company or related people | Anything about future conduct |
| `domain_age` | footprint | Domain registered 3 or more years ago (RDAP) | That the current owner is the original one |
| `https` | footprint | Valid certificate | Almost nothing, which is why it earns 0.5 |
| `policy_pages` | footprint | Privacy policy and terms both reachable | That the text was written for this company |
| `company_number_on_site` | footprint | The registry number appears on the site or its policy pages | That the number belongs to this site's operator |
| `email_domain` | reachability | Contact email on the company domain, not freemail | Much, domains are cheap |
| `phone` | reachability | Listed number answered by the company | Location |
| `address` | reachability | Office confirmed by street imagery, a visit or a video walkthrough | Ownership |
| `reviews` | reputation | 10 or more reviews, under 95% five star, no single day burst, no scam or lawsuit hits | Quality, reviews can still be bought slowly |
| `references` | reputation | 2 or more references confirmed scope, timeline and satisfaction by phone | That the references are independent, so call ones you found yourself |
| `payment_rails` | payment | At least one reversible rail such as card, PayPal or invoice terms | Honesty, only recourse |
| `pressure` | payment | No urgency wording such as act now or limited time in the offer | Much, it only flags a sales tactic |

A note on `domain_age`: RDAP measures the domain, not the business. Aged domains are bought and resold all the time, which is why it sits at medium and not high. Cross check it against the incorporation date. A company incorporated in 2026 operating on a domain registered in 2009 has a story worth hearing.

## Quick start

```bash
git clone https://github.com/SharonVivenix/check-if-a-company-is-legitimate.git
cd check-if-a-company-is-legitimate

python3 legit_check.py examples/northgate_supplies.json --today 2026-10-30   # PROCEED, exit 0
python3 legit_check.py examples/quickship_trading.json --today 2026-10-30   # VERIFY, exit 1
python3 legit_check.py --domain example.org                                 # live web layer only
python3 legit_check.py profile.json --live --json                           # profile plus live probes

python3 -m unittest discover -s tests -v
```

Both example profiles are synthetic and use the reserved `.example` domain. The red flagged one produces this:

```text
QuickShip Global Trading LLC  verdict: VERIFY  score: 0.28  expensive evidence: yes

  [+] registry_record          high    active record 7712093 in US-DE
  [?] registry_consistency     medium  registered address differs from the address on the contract, incorporated 4 months ago
  [+] screening                medium  no sanctions, PEP or adverse media hits
  [?] domain_age               medium  domain registered 0.2 years ago
  [+] https                    free    valid certificate
  [+] policy_pages             low     privacy policy and terms present
  [?] company_number_on_site   low     registration number not found on site or policy pages
  [?] email_domain             low     business contact on gmail.com
  [?] phone                    low     listed number not answered
  [?] address                  medium  mailbox address, ask where the team actually works
  [?] reviews                  medium  100% five star, real distributions have a tail, 22 reviews posted on a single day
  [x] references               high    references requested, none provided
  [x] payment_rails            medium  only irreversible rails accepted: crypto, wire
  [?] pressure                 low     urgency wording such as act now or limited time in the offer
```

Notice what the registry check did not catch. QuickShip is a real, active Delaware LLC on paper. Incorporating one takes an afternoon. Everything that exposes it sits further down the ladder: a refused reference request, crypto or wire only, a review burst, a mailbox address. A process that stops at "is it registered" would have passed it.

## Is Auto Approve a legitimate company? Running the method on a real name

"Is Auto Approve a legitimate company" is a common search for Auto Approve, a US auto loan refinance service at autoapprove.com. This repo does not certify any company. It shows how to answer the question yourself, which is the honest way to treat any "is X legit" query. Here is the live web layer, run on 2026-10-30:

```text
$ python3 legit_check.py --domain autoapprove.com
autoapprove.com  verdict: VERIFY  score: 1.00  expensive evidence: no

  [.] registry_record          high    no registry lookup recorded
  [.] screening                medium  sanctions, PEP and adverse media screening not run
  [+] domain_age               medium  domain registered 27.5 years ago
  [+] https                    free    valid certificate
  [+] policy_pages             low     privacy policy and terms present
```

Every web check passes (RDAP shows the domain registered on 1999-05-10), and the verdict is still VERIFY, because nothing expensive has been checked yet. That is the script working as designed, not a judgement on the company. To finish the job, the expensive checks for a consumer lending business are:

1. **Registry.** The site footer lists an address in St. Louis Park, Minnesota. Look the operating entity up with the Minnesota Secretary of State and with the state it is incorporated in, and confirm the status is active.
2. **Licence.** Auto refinance brokering and lending are licensed state by state in the US. Search the entity on [NMLS Consumer Access](https://www.nmlsconsumeraccess.org/) and confirm it holds a licence in your state, or that the lender it places you with does.
3. **Complaints and reputation.** The footer states an A+ rating with the BBB. Verify any claimed rating on [bbb.org](https://www.bbb.org/) directly instead of trusting the badge, and search the [CFPB Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/search/) for the company name to read complaint volume and how the company responded.
4. **Payment rails.** A refinance should run through the new lender paying off the old one. Any request to wire money, pay in gift cards or crypto, or pay a fee up front to "release" an approval fails `payment_rails` for any lender, Auto Approve or not.

Record what you find in a profile file and rerun with `--live`. The same four steps apply to any "is this lender legit" question.

## Where the evidence comes from

These are the primary sources for each layer. Most are free. Automating the identity layer across many jurisdictions is where the time goes.

| Layer | Source | Notes |
| --- | --- | --- |
| UK registry | [Companies House search](https://find-and-update.company-information.service.gov.uk/) and its [API](https://developer.company-information.service.gov.uk/) | Free key, `legit_check.py` reads it from `COMPANIES_HOUSE_API_KEY` |
| EU registries | [Find a company, European Justice portal](https://e-justice.europa.eu/content_find_a_company-489-en.do) | Search across member state registers (BRIS) |
| US public companies | [SEC EDGAR full text search](https://www.sec.gov/edgar/search/) | Private companies live in each state's Secretary of State registry |
| Australia, Singapore | [ASIC registers](https://asic.gov.au/online-services/search-asic-registers/), [ACRA](https://www.acra.gov.sg/) | |
| Legal entity identifiers | [GLEIF LEI search](https://www.gleif.org/en/lei/search) | Useful for cross border groups |
| UK financial services licence | [FCA Financial Services Register](https://register.fca.org.uk/) | A firm offering financial products that is missing here is a stop |
| US lending licence | [NMLS Consumer Access](https://www.nmlsconsumeraccess.org/) | Mortgage, consumer lending and money transmission |
| Domain registration | [ICANN lookup](https://lookup.icann.org/), [RDAP](https://about.rdap.org/) | `legit_check.py` queries RDAP through rdap.org |
| Complaints | [BBB](https://www.bbb.org/), [CFPB complaint database](https://www.consumerfinance.gov/data-research/consumer-complaints/search/) | Complaint handling tells you more than the rating |

Sanctions, PEP and adverse media screening has no free equivalent that stays current, which is why `screening` is an input field rather than a lookup. Screening every director and owner, then rescreening them, is the part that justifies a provider. iDenfy's [KYB solution](https://www.idenfy.com/know-your-business-solution/) pulls registry data, ownership and director details, runs KYC on the people behind the company, and screens them through [AML screening](https://www.idenfy.com/aml-screening/) with ongoing monitoring. Its output maps directly onto the `registry`, `screening` and `licence` blocks of a profile file. iDenfy provides the verification layer. The decision, the risk appetite and any regulatory obligation remain with your business.

## Profile schema

```json
{
  "name": "Northgate Supplies Ltd",
  "domain": "northgate-supplies.example",
  "contact_email": "accounts@northgate-supplies.example",
  "phone_answered": true,
  "address": {"type": "office | virtual | mailbox | registered_agent | residential", "verified_visually": true},
  "registry": {"jurisdiction": "GB", "company_number": "09876543", "found": true, "status": "active",
               "incorporated": "2016-03-14", "name_matches": true, "address_matches": true,
               "recent_name_changes": 0},
  "licence": {"required": false, "register": "FCA Financial Services Register", "found": null},
  "screening": {"sanctions_hit": false, "pep": false, "adverse_media": false},
  "website": {"domain_created": "2016-02-01", "https": true, "privacy_policy": true,
              "terms": true, "company_number_on_site": true},
  "reviews": {"count": 214, "five_star_share": 0.71, "max_same_day": 4, "scam_lawsuit_hits": 0},
  "references": {"requested": true, "provided": 3, "confirmed": 2},
  "payment_methods": ["invoice_net_terms", "card"],
  "pressure_language": false
}
```

Leave out any key you have not assessed and its check reports as unknown. Set `"address": null` only when the company has given no address at all, which is a fail. `found: null` on the registry or licence means "not searched yet". Dates are `YYYY-MM-DD`. A malformed date exits with code 3.

## Limits worth knowing

* The site probe reads static HTML and then tries common policy paths. A single page app that renders its footer in JavaScript is handled by the path fallback, but a site that returns the same shell for every URL can still produce a false pass on `policy_pages`. The probe requires the page to mention its subject to reduce this.
* Review signals are inputs. Scraping review platforms breaks their terms, so count and spread are recorded by hand or exported from a tool you are licensed to use.
* The weights are opinions with reasons attached. Change `FAKE_COST` or a threshold, and the tests show which verdicts moved.

## FAQ

**How do I check if a company is legit in five minutes?**
Run `--domain` for the web layer, then do the one expensive check that fits the relationship: a registry lookup for a supplier, a regulator register search for anything financial. Five minutes buys you a VERIFY with known gaps, which is better than a confident guess.

**Is a registered company automatically legitimate?**
No. Registration proves a legal entity exists. Shell and shelf companies are registered too. Registration is necessary, and the QuickShip example shows why it is not sufficient.

**What if the company refuses to give references?**
The script marks `references` as a fail. Legitimate firms with real clients can nearly always produce two. A refusal does not prove fraud, but it removes the strongest evidence available to you.

**Why does wire transfer only count as a fail?**
Because it removes recourse. A legitimate supplier may prefer wires for large invoices, so a mix of wire and card passes. Wire, crypto or gift cards as the only option fails.

## Contributing and credits

Corrections to weights, thresholds and registry sources are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Every source added to the table needs a link to the official register, not an aggregator.

The ten step method behind these checks is adapted from iDenfy's guide [How to Check if a Company is Legitimate](https://www.idenfy.com/blog/check-if-a-company-is-legitimate/), and iDenfy is the publisher of that source. The cost to fake model, the scoring rules and [legit_check.py](legit_check.py) are independent work. The Auto Approve section reports public web signals observed on 2026-10-30 and is not an assessment of the company. Nothing in this repo is legal or financial advice.

## License

MIT. See [LICENSE](LICENSE).
