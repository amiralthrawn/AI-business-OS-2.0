"""French-only interface (decision #56): the monitoring rules write French,
risk kinds are still recognised from legacy English titles, and the data
migration rewrites the English texts already stored -- exactly once."""

import importlib.util
from pathlib import Path

from app.intelligence.risks.kinds import CUSTOMER_DECLINE, MARGIN_DETERIORATION, SUPPLIER_PERFORMANCE

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "e7a1c2f4b9d3_v2_3_french_generated_texts.py"


def _migration():
    spec = importlib.util.spec_from_file_location("v23_fr", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_risk_kinds_recognise_french_and_legacy_titles():
    assert MARGIN_DETERIORATION.matches("Dégradation de marge : Frame")
    assert MARGIN_DETERIORATION.matches("Margin deterioration on product Frame")
    assert SUPPLIER_PERFORMANCE.matches("Supplier performance deterioration: Iberia")
    assert CUSTOMER_DECLINE.matches(CUSTOMER_DECLINE.title("BrightWorks Ltd"))
    assert not CUSTOMER_DECLINE.matches("Dégradation de marge : Frame")


def test_migration_translates_generated_texts_and_is_idempotent():
    m = _migration()
    cases = {
        m.translate_title: [
            ("Margin deterioration on product Steel Frame Assembly", "Dégradation de marge : Steel Frame Assembly"),
            ("Customer decline: BrightWorks Ltd", "Baisse d'activité client : BrightWorks Ltd"),
            ("Supplier cost increase of 25% on product Sensor Module", "Hausse du coût fournisseur : Sensor Module (+25\u202f%)"),
            ("Growing customer: Metroline Corp", "Client en croissance : Metroline Corp"),
        ],
        m.translate_description: [
            ("Revenue from BrightWorks Ltd fell 59.3% (from 35100 to 14300) -- possible churn risk.",
             "Le chiffre d'affaires de BrightWorks Ltd a baissé de 59,3\u202f% (de 35\u202f100 € à 14\u202f300 €) : risque de perte du client."),
            ("Margin moved from 24.8% to 13.6% (-11.2% pts) based on recent purchase and sales transactions.",
             "La marge est passée de 24,8\u202f% à 13,6\u202f% (−11,2 pts), d'après les achats et ventes récents."),
        ],
        m.translate_task_title: [("Review: Customer decline: BrightWorks Ltd", "À examiner : Baisse d'activité client : BrightWorks Ltd")],
    }
    for fn, pairs in cases.items():
        for legacy, french in pairs:
            assert fn(legacy) == french
            assert fn(french) == french  # idempotent
    # A text typed by a person is never touched.
    assert m.translate_title("Vérifier le contrat cadre Metroline") == "Vérifier le contrat cadre Metroline"
    assert m.translate_task_description("Appeler le client. Review and decide on next steps.").endswith("À examiner, puis décider de la suite.")
