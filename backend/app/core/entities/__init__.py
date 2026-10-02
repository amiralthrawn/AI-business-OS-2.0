from app.core.entities.base import Base, RelatedEntityType, ValueBasis
from app.core.entities.business_context import BusinessContext
from app.core.entities.catalog import ProductSupplier, StockKind, StockPosition
from app.core.entities.commercial_document import (
    PROCUREMENT_KINDS,
    SALES_KINDS,
    CommercialDocument,
    CommercialDocumentLine,
    CreditApplication,
    PaymentInstallment,
    CostItem,
    CostKind,
    DocumentKind,
)
from app.core.entities.communication import Communication, CommunicationDirection
from app.core.entities.company import Company
from app.core.entities.contact import Contact
from app.core.entities.customer import Customer
from app.core.entities.document import Document
from app.core.entities.event_log import EventLogEntry
from app.core.entities.intelligence_runs import AIRun, SourcingLead, WebsiteChangeProposal
from app.core.entities.object_link import ObjectLink
from app.core.entities.people import Candidate, Employee, EmployeeCostItem, SkillNeed
from app.core.entities.opportunity import Opportunity, OpportunityStatus
from app.core.entities.product import Product
from app.core.entities.risk import Risk, RiskSeverity, RiskStatus
from app.core.entities.supplier import Supplier
from app.core.entities.task import Task, TaskStatus
from app.core.entities.treasury import BankAccount, CashMovement, Shareholder
from app.core.entities.transaction import Transaction, TransactionStatus, TransactionType
from app.core.entities.user import Role, UserProfile

__all__ = [
    "Base",
    "RelatedEntityType",
    "BusinessContext",
    "Company",
    "Contact",
    "Supplier",
    "Customer",
    "Product",
    "Transaction",
    "TransactionType",
    "TransactionStatus",
    "Document",
    "Communication",
    "CommunicationDirection",
    "Task",
    "TaskStatus",
    "Risk",
    "RiskSeverity",
    "RiskStatus",
    "Opportunity",
    "OpportunityStatus",
    "EventLogEntry",
    # V2
    "ValueBasis",
    "ProductSupplier",
    "StockKind",
    "StockPosition",
    "CommercialDocument",
    "CommercialDocumentLine",
    "CreditApplication",
    "PaymentInstallment",
    "CostItem",
    "CostKind",
    "DocumentKind",
    "SALES_KINDS",
    "PROCUREMENT_KINDS",
    "ObjectLink",
    "Role",
    "UserProfile",
    # V2.1
    "Employee",
    "EmployeeCostItem",
    "SkillNeed",
    "Candidate",
    "BankAccount",
    "CashMovement",
    "Shareholder",
    "SourcingLead",
    "AIRun",
    "WebsiteChangeProposal",
]
