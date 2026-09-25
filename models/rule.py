"""
models/rule.py — SQLAlchemy ORM model for the compliance rule store.

Stores candidate regulatory rules extracted from ingested sources. Rules
progress through: draft → approved | rejected. Previous versions are never
deleted; rule_version increments on every edit. Only approved rules are
visible to the evaluator.
"""
import datetime
import uuid

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String

from .source import Base


class ComplianceRule(Base):
    """Versioned regulatory compliance rule.

    rule_data stores the full CandidateRule dict so all extracted fields
    (supporting_quote, applicability_conditions, etc.) are persisted without
    requiring a column for every future schema addition.
    """
    __tablename__ = "compliance_rules"

    # Identity & versioning
    rule_id      = Column(String(64), primary_key=True,
                          default=lambda: str(uuid.uuid4()))
    rule_version = Column(Integer, default=1,
                          doc="Incremented on every approved edit. Old versions are kept.")

    # Source linkage
    source_id    = Column(String(64), nullable=False, index=True,
                          doc="FK to SourceRegistry.source_id.")

    # Jurisdiction scope
    jurisdiction = Column(String(64),  nullable=False, index=True)
    regulator    = Column(String(128), nullable=True)
    topic        = Column(String(64),  nullable=True,
                          doc="e.g. 'leverage', 'AML', 'KYC', 'capital'.")

    # Full candidate payload
    rule_data    = Column(JSON, nullable=True,
                          doc="Full CandidateRule dict as stored JSON.")

    # Denormalized TOPSIS feed columns (for fast queries by the market ranker)
    evidence_tag     = Column(String(48), nullable=True,
                              doc="'Verified Fact' | 'Analyst Estimate' | 'Unresolved Policy / Draft'.")
    leverage_cap     = Column(String(16), nullable=True,
                              doc="e.g. '1:5', '1:300' — TOPSIS C4.")
    required_capital = Column(Float, nullable=True,
                              doc="Minimum statutory capital in USD — TOPSIS C6.")

    # Review workflow
    review_status = Column(String(32), default="draft",
                           doc="'draft' | 'approved' | 'rejected'.")
    reviewer_id   = Column(String(128), nullable=True)
    reviewed_at   = Column(DateTime, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<ComplianceRule rule_id={self.rule_id!r} "
            f"jurisdiction={self.jurisdiction!r} "
            f"review_status={self.review_status!r} "
            f"rule_version={self.rule_version}>"
        )
