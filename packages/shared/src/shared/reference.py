"""Reference data the website's hubs are built on: known organizations and hub slugs.

Kept in code (reviewed in pull requests) and written to the database by
`sync_reference_data`, an idempotent upsert run after every migration. Organizations
that are not listed here are still created automatically when a listing names them
(see shared.orgs); this list only adds the short names, aliases and official sites of
the bodies people search for by name.
"""

from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shared.orgs import normalize_alias


@dataclass(frozen=True)
class Org:
    slug: str
    name: str
    short_name: str
    kind: str  # commission | testing | force | org | university
    aliases: tuple[str, ...] = ()
    official_url: str | None = None


ORGANIZATIONS: tuple[Org, ...] = (
    # Public service commissions
    Org("ppsc", "Punjab Public Service Commission", "PPSC", "commission", (), "https://www.ppsc.gop.pk"),
    Org("fpsc", "Federal Public Service Commission", "FPSC", "commission", (), "https://www.fpsc.gov.pk"),
    Org("spsc", "Sindh Public Service Commission", "SPSC", "commission"),
    Org("kppsc", "Khyber Pakhtunkhwa Public Service Commission", "KPPSC", "commission"),
    Org("bpsc", "Balochistan Public Service Commission", "BPSC", "commission"),
    Org("ajkpsc", "Azad Jammu & Kashmir Public Service Commission", "AJKPSC", "commission"),
    # Testing services
    Org("nts", "National Testing Service", "NTS", "testing", ("National Testing Service Pakistan",), "https://www.nts.org.pk"),
    Org("pts", "Pakistan Testing Service", "PTS", "testing"),
    Org("ots", "Open Testing Service", "OTS", "testing"),
    Org("etea", "Educational Testing and Evaluation Agency", "ETEA", "testing", (), "https://www.etea.edu.pk"),
    Org("sts", "Sindh Testing Service", "STS", "testing"),
    # Forces and security
    Org("pak-army", "Pakistan Army", "Pak Army", "force", ("Join Pak Army", "Pak Army"), "https://www.joinpakarmy.gov.pk"),
    Org("pak-navy", "Pakistan Navy", "Pak Navy", "force", ("Join Pak Navy",), "https://www.joinpaknavy.gov.pk"),
    Org("paf", "Pakistan Air Force", "PAF", "force", ("Join PAF",), "https://www.joinpaf.gov.pk"),
    Org("asf", "Airports Security Force", "ASF", "force", ("Airport Security Force",)),
    Org("fia", "Federal Investigation Agency", "FIA", "force", (), "https://www.fia.gov.pk"),
    Org("ib", "Intelligence Bureau", "IB", "force"),
    Org("punjab-police", "Punjab Police", "Punjab Police", "force"),
    Org("sindh-police", "Sindh Police", "Sindh Police", "force"),
    Org("kp-police", "Khyber Pakhtunkhwa Police", "KP Police", "force", ("KPK Police",)),
    Org("islamabad-police", "Islamabad Capital Territory Police", "Islamabad Police", "force", ("ICT Police",)),
    # Federal bodies
    Org("ministry-of-defence", "Ministry of Defence", "MoD", "org", ("MOD",)),
    Org("nadra", "National Database and Registration Authority", "NADRA", "org", (), "https://www.nadra.gov.pk"),
    Org("wapda", "Water and Power Development Authority", "WAPDA", "org", (), "https://www.wapda.gov.pk"),
    Org("fbr", "Federal Board of Revenue", "FBR", "org", (), "https://www.fbr.gov.pk"),
    Org("pakistan-railways", "Pakistan Railways", "Railways", "org", (), "https://www.pakrail.gov.pk"),
    Org("pakistan-post", "Pakistan Post", "Pakistan Post", "org"),
    Org("sbp", "State Bank of Pakistan", "SBP", "org", (), "https://www.sbp.org.pk"),
    # Universities (admissions)
    Org("aiou", "Allama Iqbal Open University", "AIOU", "university", (), "https://www.aiou.edu.pk"),
)


@dataclass(frozen=True)
class Hub:
    slug: str
    kind: str  # province | region | city | field
    label: str
    # Values in listings.provinces / listings.cities / vacancies.field that belong to the hub
    matches: tuple[str, ...] = ()
    province: str | None = None  # for cities: disambiguates (Hyderabad, Sindh)
    nearby: tuple[str, ...] = field(default=())


HUBS: tuple[Hub, ...] = (
    Hub("punjab", "province", "Punjab", ("Punjab",)),
    Hub("sindh", "province", "Sindh", ("Sindh",)),
    Hub("kpk", "province", "Khyber Pakhtunkhwa", ("Khyber Pakhtunkhwa", "KPK", "KP")),
    Hub("balochistan", "province", "Balochistan", ("Balochistan",)),
    Hub("ajk", "region", "Azad Jammu & Kashmir", ("Azad Jammu and Kashmir", "Azad Kashmir", "AJK")),
    Hub("gilgit-baltistan", "region", "Gilgit-Baltistan", ("Gilgit-Baltistan", "Gilgit Baltistan", "GB")),
    Hub("islamabad", "city", "Islamabad", ("Islamabad",), None, ("rawalpindi",)),
    Hub("karachi", "city", "Karachi", ("Karachi",), "Sindh", ("hyderabad-sindh",)),
    Hub("lahore", "city", "Lahore", ("Lahore",), "Punjab", ("gujranwala", "faisalabad")),
    Hub("rawalpindi", "city", "Rawalpindi", ("Rawalpindi",), "Punjab", ("islamabad",)),
    Hub("multan", "city", "Multan", ("Multan",), "Punjab", ("bahawalpur",)),
    Hub("faisalabad", "city", "Faisalabad", ("Faisalabad",), "Punjab", ("lahore", "sargodha")),
    Hub("peshawar", "city", "Peshawar", ("Peshawar",), "Khyber Pakhtunkhwa", ("mardan",)),
    Hub("quetta", "city", "Quetta", ("Quetta",), "Balochistan"),
    Hub("hyderabad-sindh", "city", "Hyderabad (Sindh)", ("Hyderabad",), "Sindh", ("karachi", "sukkur")),
    Hub("gujranwala", "city", "Gujranwala", ("Gujranwala",), "Punjab", ("sialkot", "lahore")),
    Hub("sialkot", "city", "Sialkot", ("Sialkot",), "Punjab", ("gujranwala",)),
    Hub("sargodha", "city", "Sargodha", ("Sargodha",), "Punjab", ("faisalabad",)),
    Hub("bahawalpur", "city", "Bahawalpur", ("Bahawalpur",), "Punjab", ("multan",)),
    Hub("sukkur", "city", "Sukkur", ("Sukkur",), "Sindh", ("hyderabad-sindh",)),
    Hub("abbottabad", "city", "Abbottabad", ("Abbottabad",), "Khyber Pakhtunkhwa", ("islamabad",)),
    Hub("mardan", "city", "Mardan", ("Mardan",), "Khyber Pakhtunkhwa", ("peshawar",)),
    Hub("health", "field", "Health", ("health",)),
    Hub("it", "field", "IT & Computer", ("it",)),
    Hub("engineering", "field", "Engineering", ("engineering",)),
    Hub("teaching", "field", "Teaching & Education", ("education",)),
    Hub("finance", "field", "Finance & Accounts", ("finance",)),
    Hub("clerical", "field", "Clerical & Computer Operator", ("clerical",)),
    Hub("legal", "field", "Legal", ("legal",)),
    Hub("admin", "field", "Admin & Management", ("admin",)),
)


def sync_reference_data(session: Session) -> None:
    """Upsert ORGANIZATIONS and HUBS (idempotent). Does not commit."""
    from shared.models import HubSlug, Organization

    for o in ORGANIZATIONS:
        aliases = sorted({normalize_alias(a) for a in (o.name, o.short_name, *o.aliases)})
        stmt = insert(Organization).values(
            slug=o.slug,
            name=o.name,
            short_name=o.short_name,
            kind=o.kind,
            aliases=aliases,
            official_url=o.official_url,
            curated=True,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Organization.slug],
                set_={
                    "name": stmt.excluded.name,
                    "short_name": stmt.excluded.short_name,
                    "kind": stmt.excluded.kind,
                    "aliases": stmt.excluded.aliases,
                    "official_url": stmt.excluded.official_url,
                    "curated": True,
                    "updated_at": func.now(),
                },
            )
        )
    for h in HUBS:
        stmt = insert(HubSlug).values(
            slug=h.slug, kind=h.kind, label=h.label, matches=list(h.matches), province=h.province, nearby=list(h.nearby)
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[HubSlug.slug],
                set_={k: stmt.excluded[k] for k in ("kind", "label", "matches", "province", "nearby")},
            )
        )
