"""Unified dataset-agnostic sample representation for CAIQ vendor assessments."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceCategory(str, Enum):
    """CCM security domain taxonomy used for evaluation grouping."""

    AIS = "Application & Interface Security"
    AAC = "Audit Assurance & Compliance"
    BCR = "Business Continuity Management & Operational Resilience"
    CCC = "Change Control & Configuration Management"
    CEK = "Cryptography, Encryption & Key Management"
    DCS = "Datacenter Security"
    DSP = "Data Security & Privacy Lifecycle Management"
    GRC = "Governance, Risk & Compliance"
    HRS = "Human Resources"
    IAM = "Identity & Access Management"
    IPY = "Interoperability & Portability"
    IVS = "Infrastructure & Virtualization Security"
    LOG = "Logging & Monitoring"
    SEF = "Security Incident Management"
    STA = "Supply Chain Management"
    TVM = "Threat & Vulnerability Management"
    UEM = "Universal Endpoint Management"
    UNKNOWN = "Unknown"

    @classmethod
    def from_domain_id(cls, domain_id: str) -> "ComplianceCategory":
        """Resolve a CCM domain ID prefix (e.g. 'AIS') to its enum member."""
        prefix = domain_id.split("-")[0].upper()
        for member in cls:
            if member.name == prefix:
                return member
        return cls.UNKNOWN


class VendorAnswer(str, Enum):
    """Normalised vendor response to a CAIQ question."""

    YES = "yes"
    NO = "no"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"

    @classmethod
    def normalise(cls, raw: str) -> "VendorAnswer":
        """Map raw answer string to canonical enum value."""
        text = (raw or "").strip().lower()
        if text in {"yes", "y", "true", "1"}:
            return cls.YES
        if text in {"no", "n", "false", "0"}:
            return cls.NO
        if text in {"not applicable", "n/a", "na", "not_applicable"}:
            return cls.NOT_APPLICABLE
        return cls.UNKNOWN


@dataclass
class CAIQSample:
    """Standardised container for a single CAIQ question-answer pair from a vendor.

    Attributes
    ----------
    sample_id : str
        Unique identifier — typically ``<vendor>_<question_id>``.
    vendor : str
        The cloud service provider name.
    question_id : str
        CAIQ question identifier, e.g. ``AIS-01.1``.
    control_id : str
        Parent CCM control, e.g. ``AIS-01``.
    domain_id : str
        CCM domain prefix, e.g. ``AIS``.
    question_text : str
        The full CAIQ question.
    vendor_answer : VendorAnswer
        Normalised Yes / No / Not Applicable response.
    vendor_comment : str
        Free-text evidence provided by the vendor.
    caiq_version : str
        CAIQ version the vendor used (e.g. ``4.0.2``).
    category : ComplianceCategory
        Resolved CCM security domain.
    metadata : dict
        Additional unstructured fields (control title, domain name, etc.).
    """

    sample_id: str
    vendor: str
    question_id: str
    control_id: str
    domain_id: str
    question_text: str
    vendor_answer: VendorAnswer
    vendor_comment: str
    caiq_version: str = "unknown"
    category: ComplianceCategory = ComplianceCategory.UNKNOWN
    metadata: dict = field(default_factory=dict)

    def is_compliant(self) -> bool:
        """Return True when the vendor answered Yes."""
        return self.vendor_answer == VendorAnswer.YES

    def is_gap(self) -> bool:
        """Return True when the vendor explicitly answered No."""
        return self.vendor_answer == VendorAnswer.NO

    def to_dict(self) -> dict:
        """Serialise the sample to a plain dictionary."""
        return {
            "sample_id": self.sample_id,
            "vendor": self.vendor,
            "question_id": self.question_id,
            "control_id": self.control_id,
            "domain_id": self.domain_id,
            "question_text": self.question_text,
            "vendor_answer": self.vendor_answer.value,
            "vendor_comment": self.vendor_comment,
            "caiq_version": self.caiq_version,
            "category": self.category.value,
            "metadata": self.metadata,
        }
