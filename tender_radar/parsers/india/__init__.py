"""India: government portals (GePNIC, EESL, state search portals) and the tender-listing sites."""

from .aggregators import parse_nationaltenders_list, parse_tender18_list, parse_tenderdetail_list
from .eesl import parse_eesl_tenders
from .gepnic_org import is_captcha_page, parse_gepnic_org_list, parse_gepnic_org_tenders
from .tables import parse_generic_table, parse_gepnic_table

__all__ = [
    "is_captcha_page",
    "parse_eesl_tenders",
    "parse_generic_table",
    "parse_gepnic_org_list",
    "parse_gepnic_org_tenders",
    "parse_gepnic_table",
    "parse_nationaltenders_list",
    "parse_tender18_list",
    "parse_tenderdetail_list",
]
