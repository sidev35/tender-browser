"""Tender-listing (aggregator) sites that re-list Indian tenders: TenderDetail, Tender18, NationalTenders."""

from .nationaltenders import parse_nationaltenders_list
from .tender18 import parse_tender18_list
from .tenderdetail import parse_tenderdetail_list

__all__ = ["parse_nationaltenders_list", "parse_tender18_list", "parse_tenderdetail_list"]
